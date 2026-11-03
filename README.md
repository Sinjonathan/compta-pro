# Compta pro

Application Mac pour tenir le **décompte mensuel d'une sage-femme libérale** à partir des
exports de FSE du logiciel **Ingenus** : import et dédoublonnage des exports, déduction
automatique des cotations à partir des montants, contrôle face à Ingenus, récapitulatif
du mois (y compris en cas de remplacement), exports **.xlsx** et **PDF**.

Tout reste sur le Mac : l'app affiche son interface dans le navigateur, mais le serveur
n'écoute que l'ordinateur lui-même et les données ne quittent jamais le disque.

**[⬇︎ Télécharger la dernière version](https://github.com/Sinjonathan/compta-pro/releases/latest)**
(fichier `Compta-pro-X.Y.Z.dmg`) — Mac Apple Silicon (M1 et suivants).

---

## Installer

1. Télécharger le `.dmg` de la [dernière version](https://github.com/Sinjonathan/compta-pro/releases/latest),
   l'ouvrir et glisser **Compta pro** dans **Applications**.
2. Lancer **Compta pro**. La première fois, macOS refuse de l'ouvrir car l'app n'est pas
   signée par Apple : ouvrir **Réglages Système › Confidentialité et sécurité**, tout en bas
   « Compta pro a été bloquée » → **Ouvrir quand même**, puis confirmer. C'est à faire
   **une seule fois** (les mises à jour ne sont pas bloquées).
3. Pour lancer l'app à chaque démarrage du Mac (facultatif) :
   **Réglages Système › Général › Ouverture › +** et choisir Compta pro.

## Utiliser

### Lancer et quitter
- Lancer **Compta pro** (Applications, Launchpad ou Spotlight) : la page s'ouvre dans le
  navigateur et une icône **€** apparaît dans la barre des menus, en haut à droite.
- Page fermée par erreur : menu **€ › Ouvrir Compta pro**, ou relancer l'app.
- Quitter : menu **€ › Quitter Compta pro**.

### Importer les exports Ingenus
Bouton **Importer des exports Ingenus**, ou glisser les fichiers CSV sur la page.
Peu importe les doublons ou les exports qui se chevauchent : chaque FSE n'est comptée qu'une
fois (par son numéro) et rangée dans son mois. Les FSE antérieures au début de la compta
(**1er octobre 2026**) sont ignorées.

### Compléter le mois
Choisir le **mois** en haut ; tout est enregistré automatiquement à chaque modification.

- La **cotation**, la majoration **F** (dimanche, férié) et les **IK** sont déduites du montant
  Ingenus. Case **orange** : à vérifier (lire la note) ; case **rouge** : aucune cotation de la
  grille ne correspond. Corriger une ligne la valide ; le bouton **✓** la valide telle quelle.
- **P** (sortie précoce) n'est jamais coché automatiquement.
- **L'outil apprend des validations.** Au début il hésite souvent (C ou V à 26,50 € ?), mais
  chaque ligne validée sert aux autres, tous mois confondus : valider un seul « C » lève la
  plupart des hésitations C/V. Une proposition qui change grâce à ce nouvel apprentissage
  repasse en orange (« Proposition revue (avant : …) ») : rien ne change en silence.
- **IK km** : vide = pas de déplacement ; 0 = majoration de déplacement (MD) seule.
- **Contrôle** : « OK » quand le total (acte + frais) retrouve le montant Ingenus.
- **+ Ajouter une ligne** pour un acte facturé hors Ingenus (ajout manuel, supprimable avec 🗑).
- Trier en cliquant sur un **titre de colonne** ; élargir une colonne en glissant son bord.
- Filtres **À vérifier** / **Ajouts manuels** et recherche par patiente.
- En haut, le **récapitulatif** : totaux du mois, et partage en cas de remplacement
  (rétrocession de 25 % des actes, réglable dans les Tarifs).

### Exporter
- **Exporter .xlsx** : le décompte du mois et un onglet récapitulatif.
- **PDF** : ouvre l'impression du navigateur ; choisir « Enregistrer au format PDF ».

### Tarifs
Onglet **Tarifs** : une seule grille pour tous les mois (cotations, majorations, tiers payant,
IK, MD, taux de rétrocession).
- **Hausse de tarif** : ne pas modifier la ligne existante, **ajouter une ligne** avec la même
  cotation et la date « depuis » — les mois passés gardent l'ancien tarif.
- **Deux actes sur une même FSE** (ex. 48 € = deux SF7,5) : ajouter la cotation « 2×SF7,5 » ;
  les lignes concernées se mettent à jour.

## Mises à jour

Au lancement, l'app vérifie s'il existe une nouvelle version ; un bandeau l'annonce en haut de
la page : **Installer et redémarrer**, et c'est tout. Vérification manuelle : menu
**€ › Rechercher une mise à jour…**. Les données ne sont jamais touchées par une mise à jour.

## Données et sauvegarde

Tout est dans **Documents › Compta pro - données** (menu **€ › Ouvrir le dossier des données**) :

| Fichier | Contenu |
|---|---|
| `AAAA-MM.csv` | un fichier par mois (lisible dans Numbers ou Excel) |
| `tarifs.csv`, `parametres.csv`, `reglages.csv` | la grille et les réglages |
| `exports Ingenus/` | les exports importés |
| `sauvegardes/` | copie de chaque mois avant la première modification du jour |

**C'est ce dossier qu'il faut sauvegarder** (Time Machine, disque externe…). Il contient des
données de santé : ne pas le partager.

Ce qui sort du Mac : uniquement la vérification de version, auprès de GitHub
(`api.github.com`), au lancement de l'app.

## Limites

- Mac Apple Silicon uniquement (pas de version Intel).
- App non signée par Apple : passage unique par Réglages › Confidentialité et sécurité.

## Développement

Voir [docs/developpement.md](docs/developpement.md) (organisation du code, tests, publication
d'une version), [GLOSSARY.md](GLOSSARY.md) (vocabulaire métier) et [docs/adr/](docs/adr/)
(décisions d'architecture).
