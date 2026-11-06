# Compta pro

Comptabilité mensuelle de l'activité libérale de la titulaire (sage-femme), construite à partir des factures télétransmises par Ingenus et complétée à la main.

## Sources

**Export Ingenus**:
Fichier CSV exporté du logiciel Ingenus, listant des FSE sur une période quelconque. Plusieurs exports peuvent se chevaucher.
_Avoid_: export carte vitale, fichier FSE

**FSE**:
Une facture télétransmise par Ingenus, identifiée de façon unique par son N° Facture. Une même FSE peut apparaître dans plusieurs exports ; la version la plus récente fait foi.
_Avoid_: ligne d'export, doublon

**Ajout manuel**:
Un acte facturé hors Ingenus, saisi directement par la titulaire dans le décompte, sans FSE correspondante.
_Avoid_: ligne en plus, ligne manquante

## Décompte

**Décompte**:
Le relevé d'un mois, une ligne par acte (FSE ou ajout manuel), avec ses totaux.
_Avoid_: compta, tableur

**Cotation**:
Le code de l'acte réalisé (SF7,5, C, FCV, C+V…), qui détermine son tarif. Absente de l'export Ingenus.
_Avoid_: acte, code

**Cotation combinée**:
Une cotation regroupant plusieurs actes facturés ensemble sur une même FSE (C+SF11,6, C+DIU, C+R IMPL…), avec son propre tarif.

**Frais**:
Ce qui s'ajoute à l'acte : majorations F et P, IK (indemnités kilométriques) et MD (majoration de déplacement, celle de la grille sauf si elle est saisie à la main sur la ligne, quand le remplaçant en a facturé une autre).
_Avoid_: IF, IC

**F (férié)**:
Majoration pour un acte réalisé un dimanche ou un jour férié.

**P (sortie précoce)**:
Majoration pour le suivi d'une patiente sortie précocement de la maternité.
_Avoid_: précoce

**Montant Ingenus**:
Le montant tel qu'Ingenus l'a facturé (« Mt dépense » de la FSE).
_Avoid_: Montant Ingenius

**Contrôle**:
Vérification qu'une ligne retrouve Ingenus : le total recalculé (acte + frais) égale le Montant Ingenus.

**Ligne à vérifier**:
Ligne dont l'outil n'est pas sûr de la cotation (orange) ou n'en trouve aucune (rouge), en attente de validation par la titulaire.

**Proposition sûre**:
Cotation trouvée par l'outil sans ambiguïté, pas encore confirmée par la titulaire ; elle peut être revue (et repasser à vérifier) quand l'outil apprend de nouvelles validations.
_Avoid_: ligne validée

**Ligne pointée**:
Ligne que la titulaire a cochée, corrigée ou saisie : l'outil n'y touche plus ; seule source d'apprentissage de l'outil. Un mois ne se clôture que si toutes ses lignes sont pointées.
_Avoid_: ligne validée

**Mois clôturé**:
Mois terminé dont les montants sont figés avec la grille du jour de sa clôture ; en lecture seule, il peut être rouvert.
_Avoid_: mois validé, mois fermé

**Début de la compta**:
Premier mois géré par l'outil (octobre 2026) ; les FSE antérieures des exports sont ignorées.

**Mode de paiement**:
Comment l'acte a été réglé : 100 % (tiers payant intégral, rien payé par la patiente), CB, ESP ou CHQ (la patiente paie sa part).

**Tiers payant**:
Prise en charge directe d'une partie de l'acte par l'Assurance Maladie (70 %), la patiente ne réglant que les 30 % restants.

## Remplacement

**Titulaire**:
La sage-femme qui exerce seule et dont le numéro PS figure sur toutes les FSE.

**Remplaçant**:
Personne qui exerce à la place de la titulaire sur une période donnée.

**Rétrocession**:
Part des actes réalisés par le Remplaçant reversée à la Titulaire (25 % des actes ; le Remplaçant garde 75 % des actes et la totalité des frais).
