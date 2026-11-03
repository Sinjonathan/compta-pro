"""La grille de tarifs unique, datée (donnees/tarifs.csv et donnees/parametres.csv).

tarifs.csv     : cotation;tarif;ferie;precoce;tiers_payant;depuis
parametres.csv : cle;valeur;depuis        (ik, md, part_patiente, retrocession)

Pour un acte du jour J, on prend pour chaque cotation la ligne la plus récente
dont « depuis » ≤ J (voir docs/adr/0001).
"""
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

ENTETE_TARIFS = ["cotation", "tarif", "ferie", "precoce", "tiers_payant", "depuis"]
ENTETE_PARAMS = ["cle", "valeur", "depuis"]
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
    """La grille en vigueur à une date donnée."""
    actes: Dict[str, Acte]
    ik: float  # € par km
    md: float  # majoration de déplacement
    part_patiente: float  # part payée par la patiente en tiers payant (30 %)
    retrocession: float  # part des actes reversée à la titulaire quand elle est remplacée


def _num(s) -> float:
    return float(str(s).strip().replace(",", ".")) if str(s).strip() else 0.0


def _date(s) -> dt.date:
    s = str(s or "").strip()
    return dt.date.fromisoformat(s) if s else dt.date.min


def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "oui", "vrai", "true", "x", "✓")


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",") if x != int(x) else str(int(x))


class Tarifs:
    def __init__(self, dossier: Path):
        self.dossier = dossier
        self.lignes: List[dict] = []
        self.params: List[dict] = []
        self.recharger()

    @property
    def chemin_tarifs(self) -> Path:
        return self.dossier / "tarifs.csv"

    @property
    def chemin_params(self) -> Path:
        return self.dossier / "parametres.csv"

    def recharger(self) -> None:
        self.lignes = []
        if self.chemin_tarifs.exists():
            with open(self.chemin_tarifs, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh, delimiter=";"):
                    if not (r.get("cotation") or "").strip():
                        continue
                    self.lignes.append({
                        "cotation": r["cotation"].strip(), "tarif": _num(r["tarif"]),
                        "ferie": _num(r.get("ferie", "")), "precoce": _num(r.get("precoce", "")),
                        "tiers_payant": _bool(r.get("tiers_payant", "")), "depuis": _date(r.get("depuis")),
                    })
        self.params = []
        if self.chemin_params.exists():
            with open(self.chemin_params, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh, delimiter=";"):
                    if (r.get("cle") or "").strip():
                        self.params.append({"cle": r["cle"].strip(), "valeur": _num(r["valeur"]),
                                            "depuis": _date(r.get("depuis"))})

    def enregistrer(self) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        with open(self.chemin_tarifs, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(ENTETE_TARIFS)
            for l in sorted(self.lignes, key=lambda l: (l["cotation"], l["depuis"])):
                w.writerow([l["cotation"], _fmt(l["tarif"]), _fmt(l["ferie"]), _fmt(l["precoce"]),
                            "oui" if l["tiers_payant"] else "non",
                            "" if l["depuis"] == dt.date.min else l["depuis"].isoformat()])
        with open(self.chemin_params, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(ENTETE_PARAMS)
            for p in sorted(self.params, key=lambda p: (p["cle"], p["depuis"])):
                w.writerow([p["cle"], _fmt(p["valeur"]),
                            "" if p["depuis"] == dt.date.min else p["depuis"].isoformat()])

    def grille(self, date: dt.date) -> Grille:
        actes: Dict[str, Acte] = {}
        for l in sorted(self.lignes, key=lambda l: l["depuis"]):
            if l["depuis"] <= date:
                actes[l["cotation"]] = Acte(l["cotation"], l["tarif"], l["ferie"], l["precoce"], l["tiers_payant"])
        p = dict(PARAMS_DEFAUT)
        for x in sorted(self.params, key=lambda x: x["depuis"]):
            if x["depuis"] <= date:
                p[x["cle"]] = x["valeur"]
        return Grille(actes, p["ik"], p["md"], p["part_patiente"], p["retrocession"])

    def cotations(self) -> List[str]:
        vues = []
        for l in self.lignes:
            if l["cotation"] not in vues:
                vues.append(l["cotation"])
        return vues
