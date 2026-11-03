# Montants recalculés à la volée, tarifs datés

Les fichiers mensuels (`donnees/AAAA-MM.csv`) ne stockent que ce que la titulaire saisit ou ce qui vient d'Ingenus (cotation, F, P, km, mode, montant Ingenus…), jamais l'acte, les frais ou le total : l'application les recalcule à partir de la grille. Pour qu'une hausse de tarif ne réécrive pas les mois passés, chaque ligne de `donnees/tarifs.csv` et `donnees/parametres.csv` porte une date d'effet (`depuis`) et un acte est toujours calculé avec le tarif en vigueur à sa date.

**Considered Options** : stocker les montants calculés dans chaque ligne (simple, mais une correction de grille ne se propage plus et les fichiers peuvent devenir incohérents) ; figer une copie de la grille par mois (lourd à maintenir quand une cotation est ajoutée en cours d'année).
