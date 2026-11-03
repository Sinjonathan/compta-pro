"""Intégration des FSE Ingenus dans les fichiers mensuels, et apprentissage au fil des validations.

Ce que l'outil « sait » (Connaissances) vient uniquement des lignes déjà en base qui sont
sûres ou validées par la titulaire (sans statut orange/rouge), tous mois confondus. Chaque fois
que ce savoir change (import, validation, correction), les lignes encore à vérifier sont
réévaluées : valider une fois « C » à 26,50 € suffit à lever les autres hésitations C/V.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import cotation as cot
from donnees import Depot, Ligne
from ingenus import FSE
from tarifs import Tarifs


@dataclass
class Bilan:
    mois: str
    nouvelles: int = 0
    mises_a_jour: int = 0
    a_verifier: int = 0


# Débuts des notes écrites par l'outil (une autre note a été écrite par la titulaire : on n'y touche pas)
NOTES_OUTIL = ("Proposition revue", "Plusieurs cotations", "Aucune cotation", "Probablement", "Choisi d'après", "P ?",
               "autres possibilités")


def _combinaison(l: Ligne) -> cot.Combinaison:
    return cot.Combinaison(l.cotation, l.ferie, l.precoce, l.km)


class Connaissances:
    """Séances validées par patiente et fréquence de chaque cotation."""

    def __init__(self, depot: Depot):
        self.seances: Dict[str, List[Tuple]] = defaultdict(list)  # patiente → [(date, id, combinaison)]
        # Fréquences : lignes validées par la titulaire seulement (des propositions automatiques
        # se confirmeraient entre elles) ; à défaut, au tout début, les propositions sûres.
        self.validees: Counter = Counter()
        self.auto: Counter = Counter()
        self.statut_par_id: Dict[str, str] = {}
        for m in depot.mois_disponibles():
            for l in depot.lire(int(m[:4]), int(m[5:])):
                self.ajouter(l)
        for s in self.seances.values():
            s.sort(key=lambda x: x[0])

    def ajouter(self, l: Ligne) -> None:
        if l.cotation and not l.a_verifier:  # validées, saisies, ou proposées sûres
            self.seances[l.patiente].append((l.date, l.id, _combinaison(l)))
            (self.auto if l.statut == "auto" else self.validees)[l.cotation] += 1
            self.statut_par_id[l.id] = l.statut

    @property
    def frequences(self) -> Counter:
        return self.validees if sum(self.validees.values()) else self.auto

    def pour(self, patiente: str, date, sauf_id: Optional[str] = None):
        """(historique de la patiente, fréquences) pour proposer une cotation, sans la ligne elle-même."""
        s = [(d, c) for d, i, c in self.seances.get(patiente, []) if i != sauf_id]
        avant = [c for d, c in s if d <= date]
        hist = avant or [c for _, c in s]  # séance la plus proche en dernier
        freq = self.frequences
        propre = next((c for d, i, c in self.seances.get(patiente, []) if i == sauf_id), None) if sauf_id else None
        if propre and (self.statut_par_id.get(sauf_id) == "auto") == (freq is self.auto):
            freq = freq.copy()
            freq[propre.cotation] -= 1
        return hist, freq


def _appliquer(l: Ligne, prop: cot.Proposition) -> None:
    if prop.choix and not prop.choix.hors_grille:
        l.cotation, l.ferie, l.km = prop.choix.cotation, prop.choix.ferie, prop.choix.km
    else:
        l.cotation, l.ferie, l.km = "", False, None
    note = prop.note
    if prop.autres:
        note += (" — " if note else "") + "autres possibilités : " + ", ".join(c.libelle() for c in prop.autres[:5])
    l.note = note
    l.statut = {cot.A_VERIFIER: "orange", cot.INCONNUE: "rouge"}.get(prop.statut, "auto")


def ligne_depuis_fse(fse: FSE, tarifs: Tarifs, savoir: Connaissances) -> Ligne:
    l = Ligne(id=fse.numero, date=fse.date, patiente=fse.patiente,
              mode="100%" if fse.mode == 1 else str(fse.mode),
              montant_ingenus=fse.depense,
              regle_patiente=fse.reglement_assure if fse.mode != 1 else None,
              fse=fse.numero)
    hist, freq = savoir.pour(fse.patiente, fse.date)
    _appliquer(l, cot.proposer(fse.depense, fse.date, tarifs.grille(fse.date), hist, freq))
    return l


def integrer_mois(depot: Depot, tarifs: Tarifs, savoir: Connaissances, fses: List[FSE], annee: int, mois: int) -> Bilan:
    bilan = Bilan(f"{annee}-{mois:02d}")
    lignes = depot.lire(annee, mois)
    par_fse = {l.fse: l for l in lignes if l.fse}
    for fse in fses:
        l = par_fse.get(fse.numero)
        if l is None:
            nouvelle = ligne_depuis_fse(fse, tarifs, savoir)
            savoir.ajouter(nouvelle)  # une ligne sûre renseigne les suivantes
            lignes.append(nouvelle)
            par_fse[fse.numero] = nouvelle
            bilan.nouvelles += 1
        else:
            # Seules les données Ingenus sont rafraîchies ; les saisies de la titulaire restent.
            regle = fse.reglement_assure if fse.mode != 1 else None
            if (l.montant_ingenus is None or abs(l.montant_ingenus - fse.depense) > 0.005
                    or (regle is not None and (l.regle_patiente is None or abs(l.regle_patiente - regle) > 0.005))):
                l.montant_ingenus, l.regle_patiente = fse.depense, regle
                bilan.mises_a_jour += 1
    if bilan.nouvelles or bilan.mises_a_jour or not depot.chemin(annee, mois).exists():
        depot.ecrire(annee, mois, lignes)
    return bilan


def reevaluer(depot: Depot, tarifs: Tarifs, max_tours: int = 5) -> Dict[str, int]:
    """Repropose une cotation pour chaque ligne Ingenus que la titulaire n'a pas encore touchée.

    Les lignes à vérifier (orange/rouge) sont recalculées librement. Une ligne « auto »
    (proposée sûre) dont la proposition change passe en orange, avec l'ancienne
    proposition en note : rien ne change en silence. On recommence tant que des lignes
    deviennent sûres, puisqu'elles renseignent à leur tour les autres.
    """
    changees: Counter = Counter()
    for _ in range(max_tours):
        savoir = Connaissances(depot)
        progres = False
        for m in depot.mois_disponibles():
            a, mo = int(m[:4]), int(m[5:])
            lignes = depot.lire(a, mo)
            modif = False
            for l in lignes:
                if not (l.statut and l.fse and l.montant_ingenus is not None):
                    continue  # validée / saisie par la titulaire, ou ajout manuel
                if l.note and not l.note.startswith(NOTES_OUTIL):
                    continue  # la titulaire a annoté la ligne : elle s'en occupe
                avant = (l.cotation, l.ferie, l.km, l.statut, l.note)
                ancienne = cot.Combinaison(l.cotation, l.ferie, l.precoce, l.km)
                hist, freq = savoir.pour(l.patiente, l.date, sauf_id=l.id)
                prop = cot.proposer(l.montant_ingenus, l.date, tarifs.grille(l.date), hist, freq)
                etait_auto = l.statut == "auto"
                revue = l.note[:l.note.index(")") + 1] if l.note.startswith("Proposition revue") else ""
                _appliquer(l, prop)
                if revue:  # déjà révisée : elle reste à vérifier tant que la titulaire ne l'a pas vue
                    l.statut = "orange"
                    l.note = revue + (" — " + l.note if l.note else "")
                elif etait_auto and (l.cotation, l.ferie, l.km) != (ancienne.cotation, ancienne.ferie, ancienne.km):
                    l.statut = "orange"
                    l.note = f"Proposition revue (avant : {ancienne.libelle()})" + (" — " + l.note if l.note else "")
                if (l.cotation, l.ferie, l.km, l.statut, l.note) != avant:
                    modif = True
                    changees[m] += 1
                    progres = progres or (avant[3] in ("orange", "rouge") and l.statut == "auto")
            if modif:
                depot.ecrire(a, mo, lignes)
        if not progres:
            break
    return dict(changees)


def integrer(depot: Depot, tarifs: Tarifs, fses: Iterable[FSE]) -> Tuple[List[Bilan], int]:
    """Range chaque FSE dans son mois (ordre chronologique), puis réévalue les lignes à vérifier.

    Les FSE antérieures au début de la compta (réglage « debut ») sont ignorées ;
    renvoie (bilans, nombre de FSE ignorées).
    """
    par_mois: Dict[Tuple[int, int], List[FSE]] = defaultdict(list)
    ignorees = 0
    for f in fses:
        if f"{f.date.year}-{f.date.month:02d}" >= depot.debut:
            par_mois[(f.date.year, f.date.month)].append(f)
        else:
            ignorees += 1
    savoir = Connaissances(depot)
    bilans = [integrer_mois(depot, tarifs, savoir, sorted(par_mois[k], key=lambda f: (f.date, f.numero)), *k)
              for k in sorted(par_mois)]
    if any(b.nouvelles for b in bilans):
        reevaluer(depot, tarifs)
    for b in bilans:
        b.a_verifier = sum(1 for l in depot.lire(int(b.mois[:4]), int(b.mois[5:])) if l.a_verifier)
    return bilans, ignorees
