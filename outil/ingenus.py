"""Lecture des exports Ingenus : fusion de tous les CSV et dédoublonnage des FSE."""
import csv
import datetime as dt
import os
import unicodedata
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


def _cle(titre: str) -> str:
    """« N° Facture » → « nfacture » : titres de colonnes comparés sans accents, espaces ni signes."""
    t = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in t if c.isalnum())


# Colonnes utiles, repérées par leur titre (Ingenus en ajoute parfois, ex. « N° PS remplaçant »)
COLONNES = {"numero": "nfacture", "date": "date", "patiente": "patient", "depense": "mtdepense",
            "reglement_assure": "reglementassure", "mode": "modereglement"}


def lire_fichier(chemin: Path) -> List[FSE]:
    with open(chemin, encoding="cp1252", errors="replace", newline="") as fh:
        lignes = list(csv.reader(fh, delimiter=";"))
    if not lignes:
        return []
    titres = {_cle(t): i for i, t in enumerate(lignes[0])}
    manquantes = [k for k in COLONNES.values() if k not in titres]
    if manquantes:
        raise ValueError(f"colonnes introuvables dans l'en-tête : {', '.join(manquantes)}")
    col = {nom: titres[cle] for nom, cle in COLONNES.items()}
    fses = []
    for x in lignes[1:]:
        if len(x) <= max(col.values()) or not x[col["numero"]].strip():
            continue
        mode_brut = x[col["mode"]].strip()
        fses.append(FSE(
            numero=x[col["numero"]].strip(),
            date=dt.datetime.strptime(x[col["date"]].strip(), "%d/%m/%Y").date(),
            patiente=" ".join(x[col["patiente"]].split()).upper(),
            depense=_montant(x[col["depense"]]),
            reglement_assure=_montant(x[col["reglement_assure"]]),
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

