# Développement, publication, mises à jour

## Organisation du dépôt

```
outil/             le code (Python + ui/), outil/defaut/ = grille et réglages de départ
  app.py           point d'entrée de l'app (icône « € » dans la barre des menus + navigateur)
  compta.py        ligne de commande (développement) : interface, importer
  maj.py           mises à jour depuis les releases GitHub (constante DEPOT)
dev/
  construire.sh    construit dist/Compta pro.app, le .dmg et le .zip
  publier.sh       construit + tag git + release GitHub
  icone.py         dessine l'icône de l'app (fond noir, « € » blanc)
  essai.command    lance l'interface depuis les sources sur une base d'essai
  essai/           base d'essai locale ← PRIVÉE, ignorée par git (données de santé)
pyproject.toml     dépendances (openpyxl, rumps ; PyInstaller, Pillow pour la compilation)
uv.lock            leurs versions figées ; .python-version : Python 3.12 (géré par uv)
docs/adr/          décisions d'architecture ; GLOSSARY.md : vocabulaire
README.md          présentation et mode d'emploi (page d'accueil GitHub, lien « Mode d'emploi » de l'app)
```

Les **données** ne sont jamais dans l'app : `~/Documents/Compta pro - données/` (créé au premier
lancement depuis `outil/defaut/`). Le dépôt est **public** : rien de privé ne doit y entrer
(vérifier `git status` avant chaque commit ; `.gitignore` exclut les CSV hors `outil/defaut/`).

## Prérequis (Mac de développement)

`brew install uv gh` puis `gh auth login`. `uv sync` crée l'environnement `.venv/` (Python 3.12
téléchargé par uv, dépendances de `uv.lock`) ; les scripts de `dev/` le font d'eux-mêmes.
Mettre à jour une dépendance : `uv lock --upgrade-package <nom>`, tester, commiter `uv.lock`.

## Tester

- `dev/essai.command` : l'interface depuis les sources, sur la base d'essai `dev/essai/`
  (créée au premier lancement ; y déposer des exports dans `dev/essai/exports Ingenus/`).
  Pour tester sur des mois antérieurs au début de la compta, modifier `dev/essai/reglages.csv`.
- `dev/essai.command importer` : import en ligne de commande.
- Base d'essai vierge : supprimer le dossier `dev/essai/`.
- L'app construite, sans toucher aux vraies données de ce Mac :
  `HOME=/tmp/faux "dist/Compta pro.app/Contents/MacOS/Compta pro"`.

## Publier une version

1. Modifier, tester, commiter.
2. `dev/publier.sh 1.0.1 "Ce qui change"` (1.0.1 correctif, 1.1.0 nouveauté) : construit l'app
   avec cette version, pousse le tag `v1.0.1`, crée la release avec `Compta-pro-1.0.1.dmg` et
   `Compta-pro-1.0.1.zip`. Le texte est montré à la titulaire.

La version n'est écrite nulle part dans le code : c'est le tag git. `dev/construire.sh X.Y.Z`
l'inscrit dans l'app (fichier généré `outil/_version.py`) ; depuis les sources, elle vaut « dev »
et la recherche de mise à jour est désactivée.

Sur son Mac, l'app voit la nouvelle version au lancement (bandeau dans la page) ou via
« Rechercher une mise à jour… » dans le menu « € » : un clic télécharge le .zip, remplace
`/Applications/Compta pro.app` et relance l'app. Les données ne sont pas touchées.

## Première installation chez elle

Lui envoyer le lien https://github.com/Sinjonathan/compta-pro/releases/latest : la procédure
(dont le passage unique par Réglages › Confidentialité et sécurité) est dans le README.

## Compatibilité des données entre versions

Les fichiers de données sont des CSV à en-tête (`donnees.py` : `ENTETE`). Pour ajouter une
colonne, la lire avec une valeur par défaut quand elle manque (`r.get(...)`) : les anciens
fichiers restent lisibles et sont réécrits au nouveau format à la première modification.
Ne jamais renommer ni supprimer une colonne sans prévoir la lecture de l'ancien nom.
La grille de `outil/defaut/` n'est copiée qu'au premier lancement : un changement de grille
pour une installation existante se fait dans l'onglet Tarifs (ou par une migration dans le code).

## Limites connues

- App construite pour Mac Apple Silicon uniquement (pas Intel).
- Sans signature Apple : passage unique par Réglages › Confidentialité et sécurité.
