"""Export d'un mois en .xlsx (valeurs, pas de formules : l'application fait les calculs)."""
import io
from typing import List

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from donnees import Ligne, calculer, recapituler
from tarifs import Tarifs

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]
COLONNES = [("Date", 11), ("Patiente", 28), ("Cotation", 11), ("F", 4), ("P", 4), ("IK (km)", 8),
            ("MD (€)", 8), ("F/P (€)", 8), ("Acte (€)", 9), ("Frais (€)", 9), ("Total (€)", 10),
            ("Mode", 7), ("Réglé patiente (€)", 11), ("Ingenus (€)", 11), ("Contrôle", 11),
            ("N° FSE", 11), ("Note", 50)]
EUROS = '#,##0.00 "€"'


def exporter_mois(lignes: List[Ligne], tarifs: Tarifs, annee: int, mois: int) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Décompte {annee}-{mois:02d}"
    entete = PatternFill("solid", fgColor="FFF2CC")
    orange, rouge = PatternFill("solid", fgColor="FFD966"), PatternFill("solid", fgColor="F4A6A6")
    for i, (titre, largeur) in enumerate(COLONNES, start=1):
        c = ws.cell(1, i, titre)
        c.font, c.fill = Font(bold=True), entete
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = largeur
    for r, l in enumerate(sorted(lignes, key=lambda l: l.date), start=2):
        k = calculer(l, tarifs)
        valeurs = [l.date, l.patiente, l.cotation, "✓" if l.ferie else "", "✓" if l.precoce else "",
                   l.km, k["md"], k["fp"], k["acte"], k["frais"], k["total"], l.mode,
                   k["patiente"] if l.mode != "100%" else None, l.montant_ingenus, k["controle"],
                   l.fse, l.note]
        for i, v in enumerate(valeurs, start=1):
            ws.cell(r, i, v)
        ws.cell(r, 1).number_format = "dd/mm/yyyy"
        for i in (7, 8, 9, 10, 11, 13, 14):
            ws.cell(r, i).number_format = EUROS
        if l.a_verifier:
            ws.cell(r, 3).fill = orange if l.statut == "orange" else rouge
        if k["controle"] == "à vérifier":
            ws.cell(r, 15).fill = rouge
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(COLONNES))}{max(len(lignes) + 1, 2)}"

    rec = recapituler(lignes, tarifs, annee, mois)
    rs = wb.create_sheet("Récapitulatif")
    rs.column_dimensions["A"].width, rs.column_dimensions["B"].width = 42, 16
    rs["A1"] = f"Récapitulatif — {MOIS_FR[mois - 1]} {annee}"
    rs["A1"].font = Font(bold=True, size=14)
    lignes_recap = [
        ("Total actes", rec["total_actes"], EUROS), ("Total frais (F/P, MD, IK)", rec["total_frais"], EUROS),
        ("Titulaire (seule)", rec["titulaire_seule"], EUROS), None,
        ("Si la titulaire est remplacée", None, None),
        ("Taux de rétrocession", rec["taux_retrocession"], "0%"),
        ("Titulaire (rétrocession)", rec["titulaire_remplacee"], EUROS),
        ("Remplaçant (actes − rétrocession + frais)", rec["remplacant"], EUROS), None,
        ("Contrôles", None, None),
        ("Total Ingenus (FSE)", rec["total_ingenus"], EUROS),
        ("Lignes en écart avec Ingenus", rec["ecarts_ingenus"], "0"),
        ("Cotations à vérifier", rec["a_verifier"], "0"),
        ("Ajouts manuels", rec["ajouts_manuels"], "0"),
        ("Nombre de lignes", rec["nb_lignes"], "0"),
    ]
    r = 3
    for item in lignes_recap:
        if item:
            label, val, fmt = item
            rs.cell(r, 1, label)
            if val is None:
                rs.cell(r, 1).font = Font(bold=True, size=12)
            else:
                rs.cell(r, 2, val).number_format = fmt
                if label.startswith(("Titulaire", "Remplaçant")):
                    rs.cell(r, 1).font = rs.cell(r, 2).font = Font(bold=True)
        r += 1
    rs["A5"].border = rs["B5"].border = Border(top=Side(style="thin"))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
