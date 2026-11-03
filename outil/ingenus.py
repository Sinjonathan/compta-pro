"""Lecture des exports Ingenus : fusion de tous les CSV et dédoublonnage des FSE."""
import csv
import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

MODES = {"": 1, "CB": "CB", "Chèque": "CHQ", "Espèces": "ESP"}


@dataclass
class FSE:
    numero: str
    date: dt.date
    patiente: str
    depense: float  # Mt dépense : total facturé
    reglement_assure: float  # ce que la patiente a payé
    mode: object  # 1 (=100 %), "CB", "CHQ", "ESP"


def _montant(s: str) -> float:
    s = s.strip()
    return float(s.replace(",", ".")) if s else 0.0


def lire_fichier(chemin: Path) -> List[FSE]:
    with open(chemin, encoding="cp1252", errors="replace", newline="") as fh:
        lignes = list(csv.reader(fh, delimiter=";"))
    fses = []
    for x in lignes[1:]:
        if len(x) < 12 or not x[2].strip():
            continue
        mode_brut = x[10].strip()
        fses.append(FSE(
            numero=x[2].strip(),
            date=dt.datetime.strptime(x[3].strip(), "%d/%m/%Y").date(),
            patiente=" ".join(x[5].split()).upper(),
            depense=_montant(x[6]),
            reglement_assure=_montant(x[9]),
            mode=MODES.get(mode_brut, mode_brut),
        ))
    return fses


def charger_exports(dossier: Path) -> Dict[str, FSE]:
    """Toutes les FSE de tous les exports, une seule fois chacune.

    Quand une FSE apparaît dans plusieurs exports, la version de l'export le plus
    récent (date de modification du fichier) fait foi.
    """
    fichiers = sorted(
        (p for p in dossier.iterdir() if p.suffix.lower() == ".csv"),
        key=lambda p: os.path.getmtime(p),
    )
    fses: Dict[str, FSE] = {}
    for f in fichiers:
        for fse in lire_fichier(f):
            fses[fse.numero] = fse
    return fses

