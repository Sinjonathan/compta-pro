"""Petit serveur local (127.0.0.1 uniquement) : l'interface et son API JSON."""
import datetime as dt
import json
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import maj
from donnees import MODES, Depot, Ligne, ligne_en_dict, recapituler
from export_xlsx import exporter_mois
from fusion import NOTES_OUTIL, integrer, reevaluer
from ingenus import charger_exports, lire_fichier
from tarifs import Tarifs, _date

UI = Path(__file__).resolve().parent / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}
CHAMPS_SAISIS = {"date", "patiente", "cotation", "ferie", "precoce", "km", "mode", "montant_ingenus"}
verrou = threading.Lock()


class Appli:
    def __init__(self, exports: Path, depot: Depot, tarifs: Tarifs, version: str = "?"):
        self.exports, self.depot, self.tarifs, self.version = exports, depot, tarifs, version
        self.maj = maj.Verificateur(version)
        self.arreter = None  # fonction d'arrêt fournie par l'app (pour la mise à jour)

    # -------------------------------------------------- mois
    def mois(self, cle: str) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        lignes = self.depot.lire(a, m)
        return {"mois": cle, "lignes": [ligne_en_dict(l, self.tarifs) for l in lignes],
                "recap": recapituler(lignes, self.tarifs, a, m)}

    def modifier(self, cle: str, id_: str, champs: dict) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        lignes = self.depot.lire(a, m)
        l = next((x for x in lignes if x.id == id_), None)
        if l is None:
            raise KeyError("ligne introuvable")
        touche = False
        for k, v in champs.items():
            if k == "date":
                v = dt.date.fromisoformat(v)
            elif k == "km":
                v = None if v in (None, "") else int(float(v))
            elif k == "montant_ingenus":
                if l.fse:
                    continue  # la donnée Ingenus ne se modifie pas
                v = None if v in (None, "") else float(str(v).replace(",", "."))
            elif k in ("ferie", "precoce"):
                v = bool(v)
            elif k == "patiente":
                v = " ".join(str(v).split()).upper()
            elif k not in ("cotation", "mode", "note", "statut"):
                continue
            if getattr(l, k) != v:
                setattr(l, k, v)
                touche = touche or k in CHAMPS_SAISIS
        if (touche and "statut" not in champs) or champs.get("statut") == "":
            l.statut = ""  # la titulaire a corrigé ou validé la ligne
            if l.note.startswith(NOTES_OUTIL) and "note" not in champs:
                l.note = ""  # la remarque de l'outil n'a plus lieu d'être
        if (l.date.year, l.date.month) != (a, m):  # changement de mois : on déplace la ligne
            lignes.remove(l)
            autre = self.depot.lire(l.date.year, l.date.month)
            self.depot.ecrire(l.date.year, l.date.month, autre + [l])
        self.depot.ecrire(a, m, lignes)
        rep = self.mois(cle) if not touche else None
        if touche or champs.get("statut") == "":
            # Le savoir de l'outil a changé : les lignes encore à vérifier en profitent.
            changees = reevaluer(self.depot, self.tarifs)
            rep = self.mois(cle)
            rep["reevaluees"] = sum(changees.values())
        return rep

    def ajouter(self, cle: str, champs: dict) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        lignes = self.depot.lire(a, m)
        date = dt.date.fromisoformat(champs["date"]) if champs.get("date") else dt.date(a, m, 1)
        l = Ligne(id=Ligne.nouvel_id(), date=date, patiente=" ".join(str(champs.get("patiente", "")).split()).upper())
        self.depot.ecrire(a, m, lignes + [l])
        rep = self.mois(cle)
        rep["nouvelle"] = l.id
        return rep

    def supprimer(self, cle: str, id_: str) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        lignes = self.depot.lire(a, m)
        l = next((x for x in lignes if x.id == id_), None)
        if l is None:
            raise KeyError("ligne introuvable")
        if l.fse:
            raise ValueError("Une ligne Ingenus ne peut pas être supprimée (elle reviendrait au prochain import).")
        lignes.remove(l)
        self.depot.ecrire(a, m, lignes)
        return self.mois(cle)

    # -------------------------------------------------- imports
    def importer(self, nom: str, contenu: bytes) -> dict:
        self.exports.mkdir(exist_ok=True)
        nom = re.sub(r"[^\w .()-]", "_", Path(nom).name) or "export.csv"
        cible = self.exports / f"{dt.datetime.now():%Y-%m-%d_%Hh%M%S}_{nom}"
        cible.write_bytes(contenu)
        try:
            if not lire_fichier(cible):
                raise ValueError("aucune FSE trouvée")
            fses = charger_exports(self.exports)
        except Exception as e:
            cible.unlink()
            raise ValueError(f"{nom} n'est pas un export Ingenus lisible ({e}).")
        bilans, ignorees = integrer(self.depot, self.tarifs, fses.values())
        return {"bilans": [b.__dict__ for b in bilans if b.nouvelles or b.mises_a_jour],
                "ignorees": ignorees, "debut": self.depot.debut, "mois": self.depot.mois_disponibles()}

    # -------------------------------------------------- tarifs
    def lire_tarifs(self) -> dict:
        f = lambda d: "" if d == dt.date.min else d.isoformat()  # noqa: E731
        return {"actes": [dict(l, depuis=f(l["depuis"])) for l in self.tarifs.lignes],
                "parametres": [dict(p, depuis=f(p["depuis"])) for p in self.tarifs.params]}

    def ecrire_tarifs(self, d: dict) -> dict:
        num = lambda x: float(str(x).replace(",", ".")) if str(x).strip() else 0.0  # noqa: E731
        self.tarifs.lignes = [{"cotation": str(l["cotation"]).strip(), "tarif": num(l["tarif"]),
                               "ferie": num(l.get("ferie", 0)), "precoce": num(l.get("precoce", 0)),
                               "tiers_payant": bool(l.get("tiers_payant")), "depuis": _date(l.get("depuis"))}
                              for l in d.get("actes", []) if str(l.get("cotation", "")).strip()]
        self.tarifs.params = [{"cle": p["cle"], "valeur": num(p["valeur"]), "depuis": _date(p.get("depuis"))}
                              for p in d.get("parametres", []) if p.get("cle")]
        self.tarifs.enregistrer()
        self.tarifs.recharger()
        rep = self.lire_tarifs()
        rep["reevaluees"] = sum(reevaluer(self.depot, self.tarifs).values())  # nouvelle cotation → lignes réglées
        return rep

    def etat(self) -> dict:
        return {"version": self.version, "donnees": str(self.depot.dossier),
                "maj": self.maj.disponible, "app": maj.bundle_actuel() is not None,
                "mois": self.depot.mois_disponibles(), "cotations": sorted(self.tarifs.cotations()),
                "modes": MODES, "aujourdhui": dt.date.today().isoformat()}


def fabriquer_gestionnaire(appli: Appli):
    class Gestionnaire(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencieux
            pass

        def _json(self, obj, code=200):
            corps = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def _corps(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def _route(self, methode):
            chemin = unquote(urlparse(self.path).path)
            try:
                with verrou:
                    return self._traiter(methode, chemin)
            except (KeyError, ValueError) as e:
                self._json({"erreur": str(e).strip("'\"")}, 400)
            except Exception as e:  # pragma: no cover
                self._json({"erreur": f"Erreur inattendue : {e}"}, 500)

        def _traiter(self, methode, chemin):
            m = re.fullmatch(r"/api/mois/(\d{4}-\d{2})(?:/ligne(?:/([\w-]+))?)?", chemin)
            if methode == "GET" and chemin in ("/", "/index.html"):
                return self._fichier(UI / "index.html")
            if methode == "GET" and chemin.startswith("/ui/"):
                return self._fichier(UI / chemin[4:])
            if methode == "GET" and chemin == "/api/etat":
                return self._json(appli.etat())
            if m and methode == "GET" and not chemin.endswith("ligne"):
                return self._json(appli.mois(m.group(1)))
            if m and methode == "POST":
                return self._json(appli.ajouter(m.group(1), json.loads(self._corps() or b"{}")))
            if m and m.group(2) and methode == "PUT":
                return self._json(appli.modifier(m.group(1), m.group(2), json.loads(self._corps())))
            if m and m.group(2) and methode == "DELETE":
                return self._json(appli.supprimer(m.group(1), m.group(2)))
            if chemin == "/api/import" and methode == "POST":
                nom = unquote(self.headers.get("X-Nom-Fichier", "export.csv"))
                return self._json(appli.importer(nom, self._corps()))
            if chemin == "/api/mise-a-jour" and methode == "POST":
                info = appli.maj.verifier()
                if not info:
                    return self._json({"erreur": "Aucune nouvelle version disponible."}, 400)
                self._json({"ok": True, "version": info["version"]})
                threading.Thread(target=maj.installer, args=(info["url"], appli.arreter), daemon=True).start()
                return None
            if chemin == "/api/tarifs":
                if methode == "GET":
                    return self._json(appli.lire_tarifs())
                if methode == "PUT":
                    return self._json(appli.ecrire_tarifs(json.loads(self._corps())))
            mx = re.fullmatch(r"/export/(\d{4})-(\d{2})\.xlsx", chemin)
            if mx and methode == "GET":
                a, mo = int(mx.group(1)), int(mx.group(2))
                corps = exporter_mois(appli.depot.lire(a, mo), appli.tarifs, a, mo)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f'attachment; filename="decompte-{a}-{mo:02d}.xlsx"')
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                return self.wfile.write(corps)
            self._json({"erreur": "introuvable"}, 404)

        def _fichier(self, p: Path):
            p = p.resolve()
            if UI.resolve() not in p.parents or not p.is_file():
                return self._json({"erreur": "introuvable"}, 404)
            corps = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(p.suffix, "application/octet-stream"))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_PUT(self):
            self._route("PUT")

        def do_DELETE(self):
            self._route("DELETE")

    return Gestionnaire


def port_libre(depart=8765) -> int:
    for p in range(depart, depart + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("aucun port libre")


def demarrer(exports: Path, depot: Depot, tarifs: Tarifs, version: str = "?", port=None):
    """Démarre le serveur dans un fil d'exécution ; renvoie (appli, serveur, url)."""
    appli = Appli(exports, depot, tarifs, version)
    port = port or port_libre()
    serveur = ThreadingHTTPServer(("127.0.0.1", port), fabriquer_gestionnaire(appli))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    appli.maj.surveiller()
    return appli, serveur, f"http://127.0.0.1:{port}/"


def lancer(exports: Path, depot: Depot, tarifs: Tarifs, version: str = "?", ouvrir=True, port=None):
    """Mode ligne de commande (développement) : serveur au premier plan."""
    appli, serveur, url = demarrer(exports, depot, tarifs, version, port)
    print(f"Compta pro : {url}  (Ctrl+C pour quitter)")
    if ouvrir:
        webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        serveur.shutdown()
