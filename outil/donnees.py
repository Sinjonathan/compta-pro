"""Stockage des décomptes : un CSV par mois dans donnees/, et les calculs d'une ligne.

Seules les saisies et les données Ingenus sont stockées ; acte, frais et total sont
recalculés avec la grille actuelle, ou, pour un mois clôturé, avec la copie de la grille
enregistrée à sa clôture (AAAA-MM.cloture.json) : ses montants ne bougent plus (docs/adr/0001).
"""
import csv
import datetime as dt
import json
import os
import re
import shutil
import uuid
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from tarifs import Grille, Tarifs, _bool, _num, arrondi

ENTETE = ["id", "date", "patiente", "cotation", "F", "P", "km", "mode",
          "montant_ingenus", "regle_patiente", "fse", "statut", "note", "md"]
MODES = ["100%", "CB", "CHQ", "ESP"]
NOM_MOIS = re.compile(r"^(\d{4})-(\d{2})\.csv$")


@dataclass
class Ligne:
    id: str
    date: dt.date
    patiente: str
    cotation: str = ""
    ferie: bool = False
    precoce: bool = False
    km: Optional[int] = None  # None = pas de déplacement ; 0 = MD sans km
    mode: str = "100%"
    montant_ingenus: Optional[float] = None  # « Mt dépense » de la FSE
    regle_patiente: Optional[float] = None   # « règlement assuré » de la FSE
    fse: str = ""  # vide = ajout manuel
    # "" = pointée par la titulaire (verrouillée) ; "modifiee" = corrigée ou saisie par elle, pas encore
    # pointée (l'outil n'y touche plus) ; "auto" = proposée par l'outil, jugée sûre, pas encore
    # confirmée (peut être revue) ; "orange" = à vérifier ; "rouge" = rien ne correspond ;
    # "orange-corrigee" / "rouge-corrigee" = corrigée par elle, mais cotation toujours à choisir
    statut: str = ""
    note: str = ""
    md: Optional[float] = None  # MD saisie à la main (remplaçant) ; None = celle de la grille

    @property
    def pointee(self) -> bool:
        """Vérifiée par la titulaire (validée, corrigée ou saisie) : l'outil n'y touche plus."""
        return self.statut == ""

    @property
    def a_verifier(self) -> bool:
        return self.statut.split("-")[0] in ("orange", "rouge")

    @staticmethod
    def nouvel_id() -> str:
        return "M-" + uuid.uuid4().hex[:8]

    def vers_csv(self) -> List[str]:
        f = lambda x: "" if x is None else f"{x:.2f}".replace(".", ",")  # noqa: E731
        return [self.id, self.date.isoformat(), self.patiente, self.cotation,
                "✓" if self.ferie else "", "✓" if self.precoce else "",
                "" if self.km is None else str(self.km), self.mode,
                f(self.montant_ingenus), f(self.regle_patiente), self.fse, self.statut, self.note, f(self.md)]

    @classmethod
    def depuis_csv(cls, r: Dict[str, str]) -> "Ligne":
        opt = lambda s: None if not str(s or "").strip() else _num(s)  # noqa: E731
        km = (r.get("km") or "").strip()
        return cls(
            id=r["id"], date=dt.date.fromisoformat(r["date"]), patiente=r.get("patiente", ""),
            cotation=r.get("cotation", ""), ferie=_bool(r.get("F", "")), precoce=_bool(r.get("P", "")),
            km=int(float(km.replace(",", "."))) if km else None, mode=r.get("mode") or "100%",
            montant_ingenus=opt(r.get("montant_ingenus")), regle_patiente=opt(r.get("regle_patiente")),
            fse=r.get("fse", ""), statut=r.get("statut", ""), note=r.get("note", ""), md=opt(r.get("md")))


def calculer(l: Ligne, g: Grille) -> dict:
    """Les montants d'une ligne et ses contrôles face à Ingenus."""
    a = g.actes.get(l.cotation)
    acte = a.tarif if a else 0.0
    fp = ((a.ferie if l.ferie else 0) + (a.precoce if l.precoce else 0)) if a else 0.0
    md = (g.md if l.md is None else l.md) if l.km is not None else 0.0
    ik = (l.km or 0) * g.ik
    frais = fp + md + ik
    total = acte + frais
    if l.mode == "100%":
        patiente = 0.0
    else:
        patiente = (acte * g.part_patiente if (a and a.tiers_payant) else acte) + frais
    total, patiente = arrondi(total), arrondi(patiente)  # contrôles sur les montants affichés
    ok_total = None if l.montant_ingenus is None else abs(total - l.montant_ingenus) < 0.005
    ok_patiente = None if l.regle_patiente is None or l.mode == "100%" else abs(patiente - l.regle_patiente) < 0.015
    controle = "" if ok_total is None else ("OK" if ok_total and ok_patiente is not False else "à vérifier")
    return {"acte": arrondi(acte), "fp": arrondi(fp), "md": arrondi(md), "ik": arrondi(ik),
            "frais": arrondi(frais), "total": arrondi(total), "patiente": arrondi(patiente),
            "ok_total": ok_total, "ok_patiente": ok_patiente, "controle": controle}


def recapituler(lignes: List[Ligne], g: Grille) -> dict:
    calc = [calculer(l, g) for l in lignes]
    # Calculs en décimal exact : des sommes de flottants dériveraient de quelques millièmes.
    actes = sum((Decimal(repr(c["acte"])) for c in calc), Decimal(0))
    frais = sum((Decimal(repr(c["frais"])) for c in calc), Decimal(0))
    taux = g.retrocession
    retro = (actes * Decimal(repr(taux))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "nb_lignes": len(lignes),
        "total_actes": float(actes), "total_frais": float(frais),
        "titulaire_seule": float(actes + frais),
        "taux_retrocession": taux,
        "titulaire_remplacee": float(retro),
        # Le remplaçant garde le reste : titulaire + remplaçant = total, au centime près.
        "remplacant": float(actes - retro + frais),
        "a_verifier": sum(1 for l in lignes if l.a_verifier),
        "a_pointer": sum(1 for l in lignes if not l.pointee),
        "ecarts_ingenus": sum(1 for c in calc if c["controle"] == "à vérifier"),
        "ajouts_manuels": sum(1 for l in lignes if not l.fse),
        "total_ingenus": float(sum((Decimal(repr(l.montant_ingenus or 0)) for l in lignes if l.fse), Decimal(0))),
    }


class Depot:
    """Les fichiers mensuels de donnees/, et ses réglages (donnees/reglages.csv)."""

    def __init__(self, dossier: Path):
        self.dossier = dossier
        self.dossier.mkdir(parents=True, exist_ok=True)

    @property
    def debut(self) -> str:
        """Premier mois de la compta (AAAA-MM) : les FSE antérieures sont ignorées."""
        p = self.dossier / "reglages.csv"
        if p.exists():
            with open(p, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh, delimiter=";"):
                    if (r.get("cle") or "").strip() == "debut" and (r.get("valeur") or "").strip():
                        return r["valeur"].strip()[:7]
        return "0000-00"

    def chemin(self, annee: int, mois: int) -> Path:
        return self.dossier / f"{annee}-{mois:02d}.csv"

    def mois_disponibles(self) -> List[str]:
        return sorted(m.group(0)[:7] for p in self.dossier.iterdir() if (m := NOM_MOIS.match(p.name)))

    # ---- clôture
    def _chemin_cloture(self, annee: int, mois: int) -> Path:
        return self.dossier / f"{annee}-{mois:02d}.cloture.json"

    def cloture(self, annee: int, mois: int) -> Optional[dict]:
        """{"date": "AAAA-MM-JJ", "grille": {...}} si le mois est clôturé, sinon None."""
        p = self._chemin_cloture(annee, mois)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def est_cloture(self, annee: int, mois: int) -> bool:
        return self._chemin_cloture(annee, mois).exists()

    def cloturer(self, annee: int, mois: int, grille: Grille) -> None:
        donnees = {"date": dt.date.today().isoformat(), "grille": grille.vers_dict()}
        self._chemin_cloture(annee, mois).write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")

    def rouvrir(self, annee: int, mois: int) -> None:
        p = self._chemin_cloture(annee, mois)
        if p.exists():
            self._sauvegarde_du_jour(p)
            p.unlink()

    def grille(self, annee: int, mois: int, tarifs: Tarifs) -> Grille:
        """La grille qui s'applique au mois : la copie de la clôture, ou la grille actuelle."""
        c = self.cloture(annee, mois)
        return Grille.depuis_dict(c["grille"]) if c else tarifs.grille()

    def lire(self, annee: int, mois: int) -> List[Ligne]:
        p = self.chemin(annee, mois)
        if not p.exists():
            return []
        with open(p, encoding="utf-8", newline="") as fh:
            return [Ligne.depuis_csv(r) for r in csv.DictReader(fh, delimiter=";") if r.get("id")]

    def ecrire(self, annee: int, mois: int, lignes: List[Ligne]) -> None:
        p = self.chemin(annee, mois)
        self._sauvegarde_du_jour(p)
        lignes = sorted(lignes, key=lambda l: l.date)  # tri stable : l'ordre d'un même jour est gardé
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(ENTETE)
            for l in lignes:
                w.writerow(l.vers_csv())
        os.replace(tmp, p)

    def _sauvegarde_du_jour(self, p: Path) -> None:
        """Avant la première modification du jour, une copie dans sauvegardes/AAAA-MM-JJ/."""
        if not p.exists():
            return
        d = self.dossier / "sauvegardes" / dt.date.today().isoformat()
        if not (d / p.name).exists():
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d / p.name)


def ligne_en_dict(l: Ligne, g: Grille) -> dict:
    d = asdict(l)
    d["date"] = l.date.isoformat()
    d["a_verifier"] = l.a_verifier
    d["pointee"] = l.pointee
    d["calcul"] = calculer(l, g)
    return d
