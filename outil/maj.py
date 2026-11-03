"""Mises à jour de l'app depuis les releases GitHub (dépôt public, pas d'authentification).

Chaque release « vX.Y.Z » porte un fichier « Compta-pro-X.Y.Z.zip » contenant « Compta pro.app ».
L'app vérifie au lancement ; la titulaire décide d'installer. L'installation remplace le
bundle .app en place puis relance l'app ; les données ne sont jamais touchées.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Optional

DEPOT = "Sinjonathan/compta-pro"  # dépôt GitHub dont les releases sont proposées
DELAI = 6  # secondes
INTERVALLE = 12 * 3600  # l'app vérifie au lancement, puis toutes les 12 h tant qu'elle reste ouverte


def _tuple(v: str):
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def bundle_actuel() -> Optional[Path]:
    """Le « Compta pro.app » en cours d'exécution (None quand on lance depuis les sources)."""
    if not getattr(sys, "frozen", False):
        return None
    for p in Path(sys.executable).resolve().parents:
        if p.suffix == ".app":
            return p
    return None


class Verificateur:
    def __init__(self, version: str):
        self.version = version
        self.disponible: Optional[dict] = None  # {"version", "url", "notes"}
        self.erreur = ""

    def verifier(self) -> Optional[dict]:
        if self.version == "dev":
            return None  # lancé depuis les sources : pas de mise à jour
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{DEPOT}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": "compta-pro"})
            with urllib.request.urlopen(req, timeout=DELAI) as r:
                rel = json.load(r)
        except Exception as e:  # hors ligne, GitHub indisponible… : on réessaiera au prochain lancement
            self.erreur = str(e)
            return None
        tag = rel.get("tag_name", "")
        zip_ = next((a for a in rel.get("assets", []) if a.get("name", "").endswith(".zip")), None)
        self.erreur = ""
        if zip_ and _tuple(tag) > _tuple(self.version):
            self.disponible = {"version": tag.lstrip("v"), "url": zip_["browser_download_url"],
                               "notes": (rel.get("body") or "").strip()}
        else:
            self.disponible = None
        return self.disponible

    def surveiller(self, intervalle: int = INTERVALLE):
        """Vérifie tout de suite, puis toutes les `intervalle` secondes, en arrière-plan."""
        def boucle():
            while True:
                self.verifier()
                threading.Event().wait(intervalle)
        threading.Thread(target=boucle, daemon=True).start()


def installer(url: str, apres=None) -> None:
    """Télécharge la nouvelle version, remplace le .app en cours, relance l'app.

    `apres` est appelé juste avant de quitter (pour arrêter proprement le serveur).
    """
    app = bundle_actuel()
    if app is None:
        raise RuntimeError("La mise à jour automatique ne fonctionne que depuis l'app installée.")
    tmp = Path(tempfile.mkdtemp(prefix="compta-maj-"))
    archive = tmp / "maj.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "compta-pro"})
    with urllib.request.urlopen(req, timeout=120) as r, open(archive, "wb") as f:
        shutil.copyfileobj(r, f)
    subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(tmp / "x")], check=True)
    nouveau = next((p for p in (tmp / "x").rglob("*.app") if p.name == app.name), None)
    if nouveau is None:
        raise RuntimeError("L'archive ne contient pas « Compta pro.app ».")
    # Fichier téléchargé par l'app elle-même : pas de quarantaine, mais on s'en assure.
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(nouveau)], check=False)
    ancien = tmp / "ancien.app"
    os.rename(app, ancien)  # le processus en cours continue de tourner depuis l'ancien emplacement
    try:
        shutil.move(str(nouveau), str(app))
    except Exception:
        os.rename(ancien, app)  # on remet l'ancienne version
        raise
    # Relance après notre sortie, puis nettoyage
    subprocess.Popen(["/bin/sh", "-c", f'sleep 2; open "{app}"; rm -rf "{tmp}"'],
                     start_new_session=True)
    if apres:
        apres()
    os._exit(0)
