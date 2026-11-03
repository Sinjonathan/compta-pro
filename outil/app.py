"""Point d'entrée de « Compta pro.app » : icône dans la barre des menus + interface dans le navigateur."""
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rumps  # noqa: E402
import rumps.rumps as _rumps  # noqa: E402

import maj  # noqa: E402
from compta import DONNEES_DEFAUT, preparer, version  # noqa: E402
from donnees import Depot  # noqa: E402
from serveur import demarrer  # noqa: E402
from tarifs import Tarifs  # noqa: E402


def main():
    dossier = DONNEES_DEFAUT
    preparer(dossier)
    depot, tarifs = Depot(dossier), Tarifs(dossier)
    appli, serveur, url = demarrer(dossier / "exports Ingenus", depot, tarifs, version())
    appli.arreter = serveur.shutdown
    ouvrir = lambda *_: webbrowser.open(url)  # noqa: E731

    class Delegue(_rumps.NSApp):
        # Double-clic sur l'app déjà lancée (Finder, Dock, Launchpad) : on rouvre la page.
        def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
            ouvrir()
            return True

    _rumps.NSApp = Delegue

    def rechercher(_):
        info = appli.maj.verifier()
        if info is None:
            msg = "Compta pro est à jour." if not appli.maj.erreur else \
                f"Impossible de vérifier les mises à jour (connexion internet ?).\n\n{appli.maj.erreur}"
            rumps.alert("Compta pro", f"{msg}\n\nVersion installée : {version()}")
            return
        texte = f"Nouvelle version {info['version']} (installée : {version()})."
        if info["notes"]:
            texte += "\n\n" + info["notes"][:600]
        if rumps.alert("Mise à jour disponible", texte, ok="Installer et redémarrer", cancel="Plus tard") == 1:
            threading.Thread(target=maj.installer, args=(info["url"], serveur.shutdown), daemon=True).start()

    def dossier_donnees(_):
        subprocess.run(["open", str(dossier)])

    app = rumps.App("Compta pro", title="€", quit_button="Quitter Compta pro")
    app.menu = [
        rumps.MenuItem("Ouvrir Compta pro", callback=ouvrir),
        None,
        rumps.MenuItem("Ouvrir le dossier des données", callback=dossier_donnees),
        rumps.MenuItem("Rechercher une mise à jour…", callback=rechercher),
        rumps.MenuItem(f"Version {version()}"),
    ]
    def signaler_maj(_):
        # « €• » dans la barre des menus quand une mise à jour attend (visible même page fermée)
        app.title = "€•" if appli.maj.disponible else "€"

    rumps.Timer(signaler_maj, 60).start()
    threading.Timer(0.8, ouvrir).start()
    app.run()


if __name__ == "__main__":
    main()
