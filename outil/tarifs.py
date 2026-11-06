"""La grille de tarifs unique (donnees/tarifs.csv et donnees/parametres.csv).

tarifs.csv     : cotation;tarif;ferie;precoce;tiers_payant
parametres.csv : cle;valeur        (ik, md, part_patiente, retrocession)

Une seule version par cotation : une modification vaut pour tous les mois non clôturés ;
un mois clôturé garde la copie de la grille faite à sa clôture (voir docs/adr/0001).
"""
import csv
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List


def arrondi(x: float) -> float:
    """Arrondi commercial au centime (0,005 → 0,01), sans les aléas du round() sur les flottants
    (round(259.325, 2) donne 259.32)."""
    d = Decimal(repr(x)).quantize(Decimal("1e-9"))  # efface le bruit des flottants (777.9749999999999)
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


ENTETE_TARIFS = ["cotation", "tarif", "ferie", "precoce", "tiers_payant"]
ENTETE_PARAMS = ["cle", "valeur"]
PARAMS_DEFAUT = {"ik": 0.61, "md": 10.0, "part_patiente": 0.3, "retrocession": 0.25}


@dataclass
class Acte:
    cotation: str
    tarif: float
    ferie: float
    precoce: float
    tiers_payant: bool


@dataclass
class Grille:
    actes: Dict[str, Acte]
    ik: float  # € par km
    md: float  # majoration de déplacement
    part_patiente: float  # part payée par la patiente en tiers payant (30 %)
    retrocession: float  # part des actes reversée à la titulaire quand elle est remplacée

    def vers_dict(self) -> dict:
        return {"actes": [asdict(a) for a in self.actes.values()],
                "params": {"ik": self.ik, "md": self.md, "part_patiente": self.part_patiente,
                           "retrocession": self.retrocession}}

    @classmethod
    def depuis_dict(cls, d: dict) -> "Grille":
        p = dict(PARAMS_DEFAUT, **d.get("params", {}))
        return cls({a["cotation"]: Acte(**a) for a in d.get("actes", [])},
                   p["ik"], p["md"], p["part_patiente"], p["retrocession"])


def _num(s) -> float:
    return float(str(s).strip().replace(",", ".")) if str(s).strip() else 0.0


def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "oui", "vrai", "true", "x", "✓")


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",") if x != int(x) else str(int(x))


class Tarifs:
    def __init__(self, dossier: Path):
        self.dossier = dossier
        self.lignes: List[dict] = []
        self.params: Dict[str, float] = {}
        self.recharger()

    @property
    def chemin_tarifs(self) -> Path:
        return self.dossier / "tarifs.csv"

    @property
    def chemin_params(self) -> Path:
        return self.dossier / "parametres.csv"

    def recharger(self) -> None:
        # Compatibilité : une ancienne grille datée (colonne « depuis ») garde la version la plus récente.
        par_nom: Dict[str, tuple] = {}
        if self.chemin_tarifs.exists():
            with open(self.chemin_tarifs, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh, delimiter=";"):
                    nom = (r.get("cotation") or "").strip()
                    if not nom:
                        continue
                    ligne = {"cotation": nom, "tarif": _num(r["tarif"]), "ferie": _num(r.get("ferie", "")),
                             "precoce": _num(r.get("precoce", "")), "tiers_payant": _bool(r.get("tiers_payant", ""))}
                    depuis = (r.get("depuis") or "").strip()
                    if nom not in par_nom or depuis >= par_nom[nom][0]:
                        par_nom[nom] = (depuis, ligne)
        self.lignes = [l for _, l in par_nom.values()]
        params: Dict[str, tuple] = {}
        if self.chemin_params.exists():
            with open(self.chemin_params, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh, delimiter=";"):
                    cle = (r.get("cle") or "").strip()
                    depuis = (r.get("depuis") or "").strip()
                    if cle and (cle not in params or depuis >= params[cle][0]):
                        params[cle] = (depuis, _num(r["valeur"]))
        self.params = dict(PARAMS_DEFAUT, **{k: v for k, (_, v) in params.items() if k in PARAMS_DEFAUT})

    def enregistrer(self) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        with open(self.chemin_tarifs, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(ENTETE_TARIFS)
            for l in sorted(self.lignes, key=lambda l: l["cotation"]):
                w.writerow([l["cotation"], _fmt(l["tarif"]), _fmt(l["ferie"]), _fmt(l["precoce"]),
                            "oui" if l["tiers_payant"] else "non"])
        with open(self.chemin_params, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(ENTETE_PARAMS)
            for cle in PARAMS_DEFAUT:
                w.writerow([cle, _fmt(self.params[cle])])

    def grille(self) -> Grille:
        p = self.params
        return Grille({l["cotation"]: Acte(**l) for l in self.lignes},
                      p["ik"], p["md"], p["part_patiente"], p["retrocession"])

    def cotations(self) -> List[str]:
        return sorted(l["cotation"] for l in self.lignes)
