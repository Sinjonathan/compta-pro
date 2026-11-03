"""Déduction de la cotation et des frais (F, P, MD, IK) à partir du montant Ingenus.

Montant = tarif de l'acte + F (si dimanche/férié) + P (sortie précoce)
          + [MD + IK × km]   (déplacement, km entier, 0 possible)
"""
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from tarifs import Grille

KM_MAX = 100
TOLERANCE = 0.005  # Ingenus calcule au centime près

# Statuts d'une proposition
SURE = "sure"            # une seule combinaison possible
HISTORIQUE = "historique"  # plusieurs possibles, départagées par l'historique de la patiente
A_VERIFIER = "a_verifier"  # orange
INCONNUE = "inconnue"    # rouge : aucune combinaison


@dataclass(frozen=True)
class Combinaison:
    cotation: str
    ferie: bool
    precoce: bool
    km: Optional[int]  # None = pas de déplacement ; 0 = MD sans km
    hors_grille: bool = False  # deux actes sur une FSE, sans cotation combinée dans la grille

    def libelle(self) -> str:
        s = self.cotation + (" (absente de la grille)" if self.hors_grille else "")
        if self.ferie:
            s += " +F"
        if self.precoce:
            s += " +P"
        if self.km is not None:
            s += f" +MD+{self.km}km"
        return s


@dataclass
class Proposition:
    statut: str
    choix: Optional[Combinaison]
    autres: List[Combinaison] = field(default_factory=list)
    note: str = ""


def _paques(annee: int) -> dt.date:
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(annee, mois, jour)


def jours_feries(annee: int) -> set:
    p = _paques(annee)
    fixes = [(1, 1), (5, 1), (5, 8), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)]
    return {dt.date(annee, m, j) for m, j in fixes} | {
        p + dt.timedelta(days=1), p + dt.timedelta(days=39), p + dt.timedelta(days=50)
    }


def est_ferie(d: dt.date) -> bool:
    return d.weekday() == 6 or d in jours_feries(d.year)


def _avec_deplacement(reste: float, grille: Grille) -> List[Optional[int]]:
    """Valeurs de km (None = sans déplacement) qui expliquent le reste."""
    if abs(reste) < TOLERANCE:
        return [None]
    km = round((reste - grille.md) / grille.ik)
    if 0 <= km <= KM_MAX and abs(grille.md + grille.ik * km - reste) < TOLERANCE:
        return [km]
    return []


def paires(montant: float, grille: Grille) -> List[Combinaison]:
    """Deux actes facturés sur la même FSE (2×SF7,5, C+SF7,5…) sans cotation combinée."""
    actes = list(grille.actes.values())
    noms = set(grille.actes)
    res = []
    for i, a in enumerate(actes):
        for b in actes[i:]:
            nom = f"2×{a.cotation}" if a is b else f"{a.cotation}+{b.cotation}"
            if nom in noms or f"{b.cotation}+{a.cotation}" in noms:
                continue
            for km in _avec_deplacement(round(montant - a.tarif - b.tarif, 2), grille):
                res.append(Combinaison(nom, False, False, km, hors_grille=True))
    return res


def combinaisons(montant: float, date: dt.date, grille: Grille) -> List[Combinaison]:
    ferie_possible = est_ferie(date)
    res = []
    for acte in grille.actes.values():
        for f in ([False, True] if ferie_possible else [False]):
            for p in (False, True):
                base = acte.tarif + (acte.ferie if f else 0) + (acte.precoce if p else 0)
                for km in _avec_deplacement(round(montant - base, 2), grille):
                    res.append(Combinaison(acte.cotation, f, p, km))
    return res + paires(montant, grille)


KM_LONG = 40  # au-delà, un déplacement n'est « sûr » que s'il a déjà été vu pour la patiente


def _km_bizarre(c: Combinaison, kms_connus=()) -> bool:
    """Des km non ronds ou très longs, jamais vus (à ±5 km) pour cette patiente : peu probables."""
    if c.km is None or (c.km % 5 == 0 and c.km < KM_LONG):
        return False
    return not any(abs(c.km - k) <= 5 for k in kms_connus)


def _simplicite(c: Combinaison) -> Tuple:
    # On préfère : un acte de la grille, des km « ronds » (multiples de 5), sans P,
    # sans déplacement, puis le moins de km.
    return (c.hors_grille, _km_bizarre(c), c.precoce, c.km is not None, c.km or 0)


def _frequence(nom: str, frequences: Counter) -> int:
    """Utilisations d'une cotation ; une cotation combinée (C+DIU) compte si ses parties sont utilisées."""
    if frequences[nom]:
        return frequences[nom]
    if nom.startswith("2×"):  # un double compte si l'acte simple est déjà validé
        return frequences[nom[2:]]
    parties = nom.split("+")
    if len(parties) > 1 and all(frequences[p] for p in parties):
        return min(frequences[p] for p in parties)
    return 0


def _normale(c: Combinaison, frequences: Counter, kms_connus=()) -> bool:
    """Une combinaison « normale » : de la grille (ou double d'un acte déjà vu), km plausibles, sans P."""
    if c.hors_grille:
        return c.cotation.startswith("2×") and c.km is None and _frequence(c.cotation[2:], frequences) > 0
    return not _km_bizarre(c, kms_connus) and not c.precoce


def proposer(montant: float, date: dt.date, grille: Grille,
             historique: Optional[List[Combinaison]] = None,
             frequences: Optional[Counter] = None) -> Proposition:
    """historique : combinaisons passées de la même patiente, la plus récente en dernier.
    frequences : nombre de lignes validées pour chaque cotation, toutes patientes confondues."""
    frequences = frequences or Counter()
    cands = combinaisons(montant, date, grille)
    if est_ferie(date) and any(c.ferie for c in cands):
        cands = [c for c in cands if c.ferie]  # un dimanche/férié, Ingenus applique F
    if not cands:
        note = f"Aucune cotation de la grille ne donne {montant:.2f} €"
        moitie = [c for c in combinaisons(round(montant / 2, 2), date, grille) if not c.hors_grille]
        if moitie:
            note += f" — peut-être 2 séances de {montant / 2:.2f} € ({moitie[0].libelle()})"
        return Proposition(INCONNUE, None, note=note)
    kms = {h.km for h in historique or [] if h.km is not None}
    normales = [c for c in cands if _normale(c, frequences, kms)]
    base = lambda c: c.cotation[2:] if c.cotation.startswith("2×") else c.cotation  # noqa: E731
    # Parmi les combinaisons normales, celles déjà validées l'emportent sur celles jamais vues.
    vues = [c for c in normales if _frequence(base(c), frequences) > 0]
    plausibles = vues or normales
    cands.sort(key=lambda c: (c not in plausibles, c.hors_grille, -_frequence(c.cotation, frequences)) + _simplicite(c))
    prop = None
    if len(cands) == 1 or len(plausibles) == 1:
        prop = Proposition(SURE, cands[0], cands[1:])
    else:
        for passe in reversed(historique or []):
            meme = [c for c in cands if c.cotation == passe.cotation and c.km == passe.km]
            meme = meme or [c for c in cands if c.cotation == passe.cotation]
            if len(meme) == 1:
                prop = Proposition(HISTORIQUE, meme[0], [c for c in cands if c != meme[0]],
                                   note="Choisi d'après les séances précédentes de la patiente")
                break
    if prop is None:
        prop = Proposition(A_VERIFIER, cands[0], cands[1:], note="Plusieurs cotations possibles")
    if prop.statut == SURE:
        prop.autres = []  # inutile d'encombrer le commentaire
    if prop.choix.hors_grille:
        prop.statut = A_VERIFIER
        prop.note = (f"Probablement {prop.choix.libelle()} — ajoute cette cotation combinée "
                     "dans l'onglet Tarifs" + (" — " + prop.note if prop.note else ""))
    if prop.choix.precoce:
        prop.statut = A_VERIFIER
        prop.note = (prop.note + " — " if prop.note else "") + "P ? (sortie précoce) à cocher à la main"
    return prop
