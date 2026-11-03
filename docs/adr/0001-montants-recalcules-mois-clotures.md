# Montants recalculés, grille unique, mois clôturés figés

Les fichiers mensuels (`AAAA-MM.csv`) ne stockent que ce que la titulaire saisit et ce qui vient d'Ingenus (cotation, F, P, km, mode, montant Ingenus…), jamais l'acte, les frais ou le total : l'application les recalcule à partir de la grille, qui n'a **qu'une version par cotation**. Pour qu'une compta payée ne bouge plus, un mois peut être **clôturé** : on enregistre alors à côté de lui (`AAAA-MM.cloture.json`) une copie de la grille du jour, avec laquelle ses montants sont désormais calculés ; il passe en lecture seule, n'accepte plus de FSE (signalées à l'import) et n'est plus réévalué. Une modification de la grille, y compris le renommage d'une cotation, ne touche donc que les mois non clôturés. Rouvrir un mois supprime sa copie de grille, après confirmation.

**Considered Options** : tarifs datés (une ligne par cotation et par date d'effet) — écarté : les lignes s'empilent et deviennent incompréhensibles à terme ; stocker les montants calculés dans chaque ligne — écarté : une correction de grille ne se propagerait plus aux mois en cours.

**Consequences** : un changement de tarif en cours de mois s'applique à tout le mois tant qu'il n'est pas clôturé (en pratique, la grille est changée avant de faire la compta du mois).
