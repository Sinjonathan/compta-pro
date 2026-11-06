"""Petit serveur local (127.0.0.1 uniquement) : l'interface et son API JSON."""
import datetime as dt
import json
from collections import Counter
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import maj
from donnees import MODES, Depot, Ligne, calculer, ligne_en_dict, recapituler
from export_xlsx import exporter_mois
from fusion import NOTES_OUTIL, PROPOSEES, integrer, reevaluer
from ingenus import charger_exports, lire_fichier
from tarifs import Tarifs

UI = Path(__file__).resolve().parent / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}
NOTE_DEPOINTEE = "Dépointée"
CHAMPS_SAISIS = {"date", "patiente", "cotation", "ferie", "precoce", "km", "md", "mode", "montant_ingenus"}
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
        g = self.depot.grille(a, m, self.tarifs)
        c = self.depot.cloture(a, m)
        return {"mois": cle, "lignes": [ligne_en_dict(l, g) for l in lignes],
                "recap": recapituler(lignes, g), "cloture": c["date"] if c else None, "md_grille": g.md}

    def _ouvert(self, a: int, m: int) -> None:
        if self.depot.est_cloture(a, m):
            raise ValueError(f"{m:02d}/{a} est clôturé : rouvre-le pour le modifier.")

    def modifier(self, cle: str, id_: str, champs: dict) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        self._ouvert(a, m)
        lignes = self.depot.lire(a, m)
        l = next((x for x in lignes if x.id == id_), None)
        if l is None:
            raise KeyError("ligne introuvable")
        touche = cotation_changee = False
        if champs.get("statut") == "depointee":
            # Dépointer : la ligne redevient modifiable ; l'outil n'y touche toujours pas.
            if l.pointee:
                l.statut = "modifiee"
                self.depot.ecrire(a, m, lignes)
                return self._apres_apprentissage(cle)  # l'outil désapprend cette ligne
            return self.mois(cle)
        if l.pointee and any(k != "statut" for k in champs):
            raise ValueError("Cette ligne est pointée : décoche-la pour la modifier.")
        for k, v in champs.items():
            if k == "date":
                v = dt.date.fromisoformat(v)
            elif k == "km":
                v = None if v in (None, "") else int(float(v))
            elif k == "md":
                # MD modifiée (remplaçant) ; vide ou égale à la grille = celle de la grille
                v = None if v in (None, "") else round(float(str(v).replace(",", ".")), 2)
                if v is not None and abs(v - self.depot.grille(a, m, self.tarifs).md) < 0.005:
                    v = None
                if v is not None and l.km is None and "km" not in champs:
                    l.km, touche = 0, True  # une MD suppose un déplacement
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
                cotation_changee = cotation_changee or k == "cotation"
        doute_leve = champs.get("statut") == "" or cotation_changee
        if champs.get("statut") == "":
            l.statut = ""  # pointée : la titulaire a vérifié la ligne, elle est verrouillée
        elif touche:
            # Corrigée : l'outil n'y touche plus, elle reste à pointer. Un doute sur la cotation
            # (orange/rouge) reste affiché tant qu'elle n'a pas choisi la cotation.
            couleur = l.statut.split("-")[0]
            if couleur in ("orange", "rouge") and not cotation_changee:
                l.statut = couleur + "-corrigee"
            elif l.statut in PROPOSEES or l.statut.endswith("-corrigee"):
                l.statut = "modifiee"
        if doute_leve:
            if (l.note.startswith(NOTES_OUTIL) or l.note == NOTE_DEPOINTEE) and "note" not in champs:
                l.note = ""  # la remarque de l'outil n'a plus lieu d'être
        if (l.date.year, l.date.month) != (a, m):  # changement de mois : on déplace la ligne
            self._ouvert(l.date.year, l.date.month)
            lignes.remove(l)
            autre = self.depot.lire(l.date.year, l.date.month)
            self.depot.ecrire(l.date.year, l.date.month, autre + [l])
        self.depot.ecrire(a, m, lignes)
        # L'outil n'apprend que des lignes pointées : seul un pointage change son savoir.
        return self._apres_apprentissage(cle) if champs.get("statut") == "" else self.mois(cle)

    def _apres_apprentissage(self, cle: str) -> dict:
        """Le savoir de l'outil a changé : les lignes encore à vérifier en profitent."""
        changees = reevaluer(self.depot, self.tarifs)
        rep = self.mois(cle)
        rep["reevaluees"] = sum(changees.values())
        return rep

    def ajouter(self, cle: str, champs: dict) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        self._ouvert(a, m)
        lignes = self.depot.lire(a, m)
        date = dt.date.fromisoformat(champs["date"]) if champs.get("date") else dt.date(a, m, 1)
        l = Ligne(id=Ligne.nouvel_id(), date=date, patiente=" ".join(str(champs.get("patiente", "")).split()).upper(),
                  statut="modifiee")  # saisie par la titulaire, à pointer une fois complète
        self.depot.ecrire(a, m, lignes + [l])
        rep = self.mois(cle)
        rep["nouvelle"] = l.id
        return rep

    def supprimer(self, cle: str, id_: str) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        self._ouvert(a, m)
        lignes = self.depot.lire(a, m)
        l = next((x for x in lignes if x.id == id_), None)
        if l is None:
            raise KeyError("ligne introuvable")
        if l.fse:
            raise ValueError("Une ligne Ingenus ne peut pas être supprimée (elle reviendrait au prochain import).")
        lignes.remove(l)
        self.depot.ecrire(a, m, lignes)
        return self.mois(cle)

    # -------------------------------------------------- clôture
    def cloturer(self, cle: str) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        self._ouvert(a, m)
        lignes = self.depot.lire(a, m)
        if not lignes:
            raise ValueError("Ce mois est vide.")
        reste = sum(1 for l in lignes if not l.pointee)
        if reste:
            raise ValueError(f"Il reste {reste} ligne(s) à pointer : vérifie-les et coche-les avant de clôturer.")
        self.depot.cloturer(a, m, self.tarifs.grille())
        return self.mois(cle)

    def apercu_reouverture(self, cle: str) -> dict:
        """Combien de lignes changeraient de montant si le mois reprenait la grille actuelle."""
        a, m = int(cle[:4]), int(cle[5:7])
        figee, actuelle = self.depot.grille(a, m, self.tarifs), self.tarifs.grille()
        lignes = self.depot.lire(a, m)
        changent = sum(1 for l in lignes if calculer(l, figee)["total"] != calculer(l, actuelle)["total"])
        perdues = sum(1 for l in lignes if l.cotation and l.cotation not in actuelle.actes)
        return {"lignes_changeantes": changent, "cotations_absentes": perdues}

    def rouvrir(self, cle: str) -> dict:
        a, m = int(cle[:4]), int(cle[5:7])
        self.depot.rouvrir(a, m)
        # Une cotation renommée ou supprimée depuis la clôture n'existe plus : on le signale.
        connues = set(self.tarifs.cotations())
        lignes = self.depot.lire(a, m)
        perdues = [l for l in lignes if l.cotation and l.cotation not in connues]
        for l in perdues:
            l.statut = "orange"
            l.note = (f"Cotation « {l.cotation} » absente de la grille actuelle (renommée ou supprimée "
                      "depuis la clôture) : choisir la bonne cotation")
        if perdues:
            self.depot.ecrire(a, m, lignes)
        return self.mois(cle)

    def _mois_ouverts(self):
        for k in self.depot.mois_disponibles():
            a, m = int(k[:4]), int(k[5:])
            if not self.depot.est_cloture(a, m):
                yield a, m

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
        return {"bilans": [b.__dict__ for b in bilans if b.nouvelles or b.mises_a_jour or b.hors_cloture],
                "ignorees": ignorees, "debut": self.depot.debut, "mois": self.depot.mois_disponibles()}

    # -------------------------------------------------- tarifs
    def lire_tarifs(self) -> dict:
        # « ancien » = nom à l'ouverture de l'écran : sert à reconnaître un renommage
        return {"actes": [dict(l, ancien=l["cotation"]) for l in sorted(self.tarifs.lignes, key=lambda l: l["cotation"])],
                "parametres": dict(self.tarifs.params)}

    def ecrire_tarifs(self, d: dict) -> dict:
        """Enregistre la grille. Un renommage est reporté sur les lignes des mois non clôturés ;
        une cotation utilisée dans un mois non clôturé ne peut pas être supprimée."""
        num = lambda x: float(str(x).replace(",", ".")) if str(x).strip() else 0.0  # noqa: E731
        actes = [l for l in d.get("actes", []) if str(l.get("cotation", "")).strip()]
        noms = [str(l["cotation"]).strip() for l in actes]
        doubles = sorted({n for n in noms if noms.count(n) > 1})
        if doubles:
            raise ValueError(f"Cotation en double : {', '.join(doubles)}.")
        renommages = {l["ancien"]: str(l["cotation"]).strip() for l in actes
                      if l.get("ancien") and l["ancien"] != str(l["cotation"]).strip()}
        gardees = {l.get("ancien") or str(l["cotation"]).strip() for l in actes}
        supprimees = {x["cotation"] for x in self.tarifs.lignes} - gardees
        utilisees = Counter(l.cotation for a, m in self._mois_ouverts() for l in self.depot.lire(a, m))
        bloquees = [f"{c} ({utilisees[c]} ligne(s))" for c in sorted(supprimees) if utilisees[c]]
        if bloquees:
            raise ValueError("Impossible de supprimer une cotation utilisée dans un mois non clôturé : "
                             + ", ".join(bloquees) + ".")
        renommees = 0
        if renommages:
            for a, m in self._mois_ouverts():
                lignes = self.depot.lire(a, m)
                n = 0
                for l in lignes:
                    if l.cotation in renommages:
                        l.cotation, n = renommages[l.cotation], n + 1
                if n:
                    self.depot.ecrire(a, m, lignes)
                    renommees += n
        self.tarifs.lignes = [{"cotation": str(l["cotation"]).strip(), "tarif": num(l["tarif"]),
                               "ferie": num(l.get("ferie", 0)), "precoce": num(l.get("precoce", 0)),
                               "tiers_payant": bool(l.get("tiers_payant"))} for l in actes]
        params = d.get("parametres", {})
        self.tarifs.params = {k: num(params.get(k, v)) for k, v in self.tarifs.params.items()}
        self.tarifs.enregistrer()
        self.tarifs.recharger()
        rep = self.lire_tarifs()
        rep["renommees"] = renommees
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
            mc = re.fullmatch(r"/api/mois/(\d{4}-\d{2})/(cloture|reouverture)", chemin)
            if mc and mc.group(2) == "cloture" and methode == "POST":
                return self._json(appli.cloturer(mc.group(1)))
            if mc and mc.group(2) == "cloture" and methode == "DELETE":
                return self._json(appli.rouvrir(mc.group(1)))
            if mc and mc.group(2) == "reouverture" and methode == "GET":
                return self._json(appli.apercu_reouverture(mc.group(1)))
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
                c = appli.depot.cloture(a, mo)
                corps = exporter_mois(appli.depot.lire(a, mo), appli.depot.grille(a, mo, appli.tarifs), a, mo,
                                      c["date"] if c else "")
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
