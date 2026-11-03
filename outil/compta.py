"""Compta pro.

    python compta.py                 → ouvre l'interface dans le navigateur (développement ;
                                       l'app installée passe par app.py)
    python compta.py importer        → intègre les exports Ingenus déposés dans le dossier de données

Options :
    --donnees DOSSIER   dossier de données (défaut : ~/Documents/Compta pro - données)
    --exports DOSSIER   dossier des exports Ingenus (défaut : <données>/exports Ingenus)

Le programme et les données sont séparés : une mise à jour remplace le programme
sans jamais toucher aux données.
"""
import shutil
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from donnees import Depot  # noqa: E402
from fusion import integrer  # noqa: E402
from ingenus import charger_exports  # noqa: E402
from tarifs import Tarifs  # noqa: E402

DONNEES_DEFAUT = Path.home() / "Documents" / "Compta pro - données"
DEFAUT = ICI / "defaut"  # grille et réglages de départ


def version() -> str:
    """Version inscrite par dev/construire.sh à partir du tag git ; « dev » depuis les sources."""
    try:
        from _version import VERSION
        return VERSION
    except ImportError:
        return "dev"


def preparer(dossier: Path) -> None:
    """Au premier lancement : crée le dossier de données avec la grille et les réglages de départ."""
    dossier.mkdir(parents=True, exist_ok=True)
    for f in DEFAUT.glob("*.csv"):
        if not (dossier / f.name).exists():
            shutil.copy2(f, dossier / f.name)


def cmd_importer(depot, tarifs, exports):
    fses = charger_exports(exports)
    bilans, ignorees = integrer(depot, tarifs, fses.values())
    if ignorees:
        print(f"{ignorees} FSE antérieures au début de la compta ({depot.debut}) ignorées")
    for b in bilans:
        print(f"{b.mois} : {b.nouvelles} FSE ajoutées, {b.mises_a_jour} mises à jour, {b.a_verifier} à vérifier")


def _option(args, nom):
    if nom in args:
        i = args.index(nom)
        return Path(args[i + 1]).expanduser().resolve(), args[:i] + args[i + 2:]
    return None, args


def main(args):
    dossier, args = _option(args, "--donnees")
    exports, args = _option(args, "--exports")
    dossier = dossier or DONNEES_DEFAUT
    exports = exports or dossier / "exports Ingenus"
    preparer(dossier)
    depot, tarifs = Depot(dossier), Tarifs(dossier)
    if not args:
        from serveur import lancer
        print(f"Compta pro {version()} — données : {dossier}")
        lancer(exports, depot, tarifs, version())
    elif args[0] == "importer":
        cmd_importer(depot, tarifs, exports)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
