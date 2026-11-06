"use strict";
// Compta pro — interface. Toutes les données viennent de l'API locale (serveur.py).

const MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
  "septembre", "octobre", "novembre", "décembre"];
const etat = { general: null, mois: null, donnees: null, filtre: "tout", recherche: "", tarifs: null };
const $ = (s) => document.querySelector(s);
const euros = (x) => (x == null ? "" : x.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €");
const nb = (x) => (x == null ? "" : x.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

function el(tag, attrs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of enfants.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(c));
  return e;
}

async function api(methode, url, corps, entetes = {}) {
  const opts = { method: methode, headers: entetes };
  if (corps !== undefined) {
    opts.body = corps instanceof ArrayBuffer ? corps : JSON.stringify(corps);
    if (!(corps instanceof ArrayBuffer)) opts.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(url, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.erreur || "Erreur");
  return j;
}

let minuteur;
function toast(msg, duree = 3500) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("visible");
  clearTimeout(minuteur);
  minuteur = setTimeout(() => t.classList.remove("visible"), duree);
}

function libelleMois(cle) {
  const [a, m] = cle.split("-").map(Number);
  return `${MOIS_FR[m - 1]} ${a}`;
}

// ------------------------------------------------------------------ décompte

async function chargerMois(cle) {
  etat.mois = cle;
  $("#mois").value = cle;
  try { localStorage.setItem("compta-mois", cle); } catch (e) { /* stockage indisponible */ }
  $("#btn-xlsx").href = `/export/${cle}.xlsx`;
  etat.donnees = await api("GET", `/api/mois/${cle}`);
  rendreEtatMois();
  rendreRecap();
  rendreLignes();
}

// ------------------------------------------------------------------ clôture du mois

const clos = () => Boolean(etat.donnees && etat.donnees.cloture);

function rendreEtatMois() {
  const d = etat.donnees, b = $("#btn-cloture"), e = $("#etat-mois");
  document.body.classList.toggle("mois-clos", clos());
  if (clos()) {
    e.textContent = `🔒 Clôturé le ${d.cloture.split("-").reverse().join("/")} : montants figés`;
    e.className = "etat-mois clos";
    b.textContent = "Rouvrir le mois";
  } else {
    e.textContent = d.lignes.length ? "Mois ouvert" : "";
    e.className = "etat-mois";
    b.textContent = "Clôturer le mois";
  }
  b.hidden = !d.lignes.length && !clos();
}

/** Mois clôturé : tout le tableau en lecture seule. */
function verrouiller(racine) {
  if (clos()) racine.querySelectorAll("input, select, button").forEach((x) => { x.disabled = true; });
}

async function basculerCloture() {
  const mois = libelleMois(etat.mois);
  try {
    if (clos()) {
      const { lignes_changeantes: n, cotations_absentes: p } = await api("GET", `/api/mois/${etat.mois}/reouverture`);
      const effet = (n ? `${n} ligne(s) changeront de montant avec la grille actuelle.`
        : "Aucun montant ne change avec la grille actuelle.")
        + (p ? `\n${p} ligne(s) utilisent une cotation renommée ou supprimée depuis : elles passeront à vérifier.` : "");
      if (!confirm(`Rouvrir ${mois} ? Ses montants ne seront plus figés et il redeviendra modifiable.\n\n${effet}`)) return;
      etat.donnees = await api("DELETE", `/api/mois/${etat.mois}/cloture`);
      toast(`${mois} est rouvert.`);
    } else {
      const r = etat.donnees.recap;
      if (r.a_pointer) {
        toast(`Il reste ${r.a_pointer} ligne(s) à pointer avant de clôturer ${mois} (filtre « À pointer »).`, 6000);
        return;
      }
      const ecarts = r.ecarts_ingenus ? `⚠️ ${r.ecarts_ingenus} ligne(s) ne correspondent pas à Ingenus (filtre « À vérifier »).\n\n` : "";
      if (!confirm(`${ecarts}Clôturer ${mois} ? Ses montants seront figés : une modification de la grille ne le changera plus, `
        + `et il passera en lecture seule (on peut le rouvrir).`)) return;
      etat.donnees = await api("POST", `/api/mois/${etat.mois}/cloture`);
      toast(`${mois} est clôturé.`);
    }
  } catch (e) { toast(e.message, 6000); return; }
  rendreEtatMois(); rendreRecap(); rendreLignes();
}

function rendreRecap() {
  const r = etat.donnees.recap;
  const carte = (titre, valeur, cls = "") => el("div", { class: "carte " + cls },
    el("div", { class: "titre" }, titre), el("div", { class: "valeur" }, valeur));
  $("#recap").replaceChildren(
    carte("Total actes", euros(r.total_actes)),
    carte("Total frais (F/P, MD, IK)", euros(r.total_frais)),
    carte("Titulaire (seule)", euros(r.titulaire_seule)),
    carte(`Titulaire remplacée (${Math.round(r.taux_retrocession * 100)} %)`, euros(r.titulaire_remplacee)),
    carte("Remplaçant", euros(r.remplacant)),
    carte("Lignes à pointer", String(r.a_pointer), r.a_pointer ? "alerte" : ""),
    carte("Cotations à vérifier", String(r.a_verifier), r.a_verifier ? "alerte" : ""),
    carte("Écarts avec Ingenus", String(r.ecarts_ingenus), r.ecarts_ingenus ? "alerte" : ""),
    carte("Lignes / ajouts manuels", `${r.nb_lignes} / ${r.ajouts_manuels}`),
  );
}

function visible(l) {
  if (etat.filtre === "verifier" && !(l.a_verifier || l.calcul.controle === "à vérifier")) return false;
  if (etat.filtre === "manuel" && l.fse) return false;
  if (etat.filtre === "pointer" && l.pointee) return false;
  if (etat.recherche && !l.patiente.includes(etat.recherche.toUpperCase())) return false;
  return true;
}

// Colonnes du décompte : largeur par défaut, alignement, clé de tri, contenu.
const COLONNES = [
  { cle: "date", titre: "Date", largeur: 140, tri: (l) => l.date,
    cellule: (l, ch) => el("input", { type: "date", value: l.date, "data-champ": "date", onchange: (e) => ch("date", e.target.value) }) },
  { cle: "patiente", titre: "Patiente", largeur: 220, tri: (l) => l.patiente,
    cellule: (l, ch) => el("input", { type: "text", value: l.patiente, title: l.patiente, "data-champ": "patiente", onchange: (e) => ch("patiente", e.target.value) }) },
  { cle: "cotation", titre: "Cotation", largeur: 118, tri: (l) => l.cotation, classe: (l) => "cot " + (l.statut || ""),
    cellule: (l, ch) => el("select", { "data-champ": "cotation", onchange: (e) => ch("cotation", e.target.value) }, optionsCotation(l.cotation)) },
  { cle: "ferie", titre: "F", aide: "Férié / dimanche", largeur: 40, align: "c", tri: (l) => (l.ferie ? 1 : 0),
    cellule: (l, ch) => el("input", { type: "checkbox", checked: l.ferie, "data-champ": "ferie", title: "Férié / dimanche", onchange: (e) => ch("ferie", e.target.checked) }) },
  { cle: "precoce", titre: "P", aide: "Sortie précoce", largeur: 40, align: "c", tri: (l) => (l.precoce ? 1 : 0),
    cellule: (l, ch) => el("input", { type: "checkbox", checked: l.precoce, "data-champ": "precoce", title: "Sortie précoce", onchange: (e) => ch("precoce", e.target.checked) }) },
  { cle: "km", titre: "IK km", aide: "Kilomètres aller-retour. Vide = pas de déplacement ; 0 = MD seule", largeur: 66, align: "n", tri: (l) => l.km ?? -1,
    cellule: (l, ch) => el("input", { type: "number", min: "0", step: "1", value: l.km ?? "", placeholder: "—", "data-champ": "km",
      title: "Vide = pas de déplacement ; 0 = MD seule", onchange: (e) => ch("km", e.target.value) }) },
  { cle: "md", titre: "MD", aide: "Majoration de déplacement, préremplie avec la grille dès qu'il y a un déplacement ; modifiable (remplaçant). Vider = valeur de la grille",
    largeur: 70, align: "n", tri: (l) => l.calcul.md, classe: (l) => (l.md != null ? "md-saisie" : ""),
    cellule: (l, ch) => el("input", { type: "text", inputmode: "decimal", value: l.km == null ? "" : nb(l.calcul.md), placeholder: "—", "data-champ": "md",
      title: l.md != null ? `Modifiée (grille : ${nb(etat.donnees.md_grille)})` : "Valeur de la grille — modifiable ; vider pour revenir à la grille",
      onchange: (e) => ch("md", e.target.value) }) },
  { cle: "mode", titre: "Mode", largeur: 96, tri: (l) => l.mode,
    cellule: (l, ch) => el("select", { "data-champ": "mode", onchange: (e) => ch("mode", e.target.value) },
      etat.general.modes.map((m) => el("option", { value: m, selected: m === l.mode }, m))) },
  { cle: "acte", titre: "Acte", largeur: 78, align: "n", calc: true, tri: (l) => l.calcul.acte, cellule: (l) => nb(l.calcul.acte) },
  { cle: "frais", titre: "Frais", largeur: 74, align: "n", calc: true, tri: (l) => l.calcul.frais,
    titreCellule: (l) => `F/P ${nb(l.calcul.fp)} + MD ${nb(l.calcul.md)} + IK ${nb(l.calcul.ik)}`, cellule: (l) => nb(l.calcul.frais) },
  { cle: "total", titre: "Total", largeur: 84, align: "n", calc: true, tri: (l) => l.calcul.total,
    cellule: (l) => el("strong", {}, nb(l.calcul.total)) },
  { cle: "ingenus", titre: "Ingenus", largeur: 86, align: "n", tri: (l) => l.montant_ingenus ?? -1,
    cellule: (l, ch) => (l.fse ? nb(l.montant_ingenus)
      : el("input", { type: "text", inputmode: "decimal", value: l.montant_ingenus == null ? "" : nb(l.montant_ingenus), placeholder: "—",
        "data-champ": "montant_ingenus", onchange: (e) => ch("montant_ingenus", e.target.value) })) },
  { cle: "controle", titre: "Contrôle", largeur: 96, align: "c", tri: (l) => ({ "à vérifier": 0, OK: 2 }[l.calcul.controle] ?? 1),
    cellule: (l) => (l.calcul.controle === "OK" ? el("span", { class: "badge ok" }, "OK")
      : l.calcul.controle ? el("span", { class: "badge ko", title: l.calcul.ok_total === false ? `Total ${euros(l.calcul.total)} ≠ Ingenus` : "Part patiente ≠ Ingenus" }, "à vérifier")
      : "") },
  { cle: "fse", titre: "N° FSE", largeur: 96, tri: (l) => l.fse || "~",
    cellule: (l) => el("span", { class: "fse" }, l.fse || "manuel") },
  { cle: "note", titre: "Note", largeur: 360, tri: (l) => l.note,
    cellule: (l, ch) => el("input", { type: "text", class: "note", value: l.note, title: l.note, "data-champ": "note", onchange: (e) => ch("note", e.target.value) }) },
  { cle: "pointee", titre: "✓", aide: "Pointé : ligne vérifiée, l'outil n'y touche plus. Toutes les lignes doivent être pointées pour clôturer le mois",
    largeur: 64, align: "c", tri: (l) => (l.pointee ? 1 : 0),
    cellule: (l) => [
      el("input", { type: "checkbox", checked: l.pointee, "data-champ": "pointee",
        title: l.pointee ? "Pointée — décocher pour la revoir" : "Pointer : la ligne est juste, l'outil n'y touchera plus",
        onchange: (e) => pointer(l, e.target) }),
      !l.fse ? el("button", { class: "icone", title: "Supprimer cet ajout manuel", onclick: () => supprimer(l) }, "🗑") : null] },
];

const memo = {
  lire(cle, defaut) { try { return JSON.parse(localStorage.getItem(cle)) ?? defaut; } catch (e) { return defaut; } },
  ecrire(cle, v) { try { localStorage.setItem(cle, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
};

// Tableau à colonnes triables (clic sur l'en-tête) et redimensionnables (bord de l'en-tête),
// réglages mémorisés dans le navigateur. Utilisé par le décompte et la grille des actes.
function tableTriable({ selecteur, colonnes, memoCle, rafraichir }) {
  const t = {
    tri: memo.lire(memoCle + "-tri", { cle: null, sens: 1 }),
    largeurs: memo.lire(memoCle + "-largeurs", {}),
  };
  const largeur = (c) => t.largeurs[c.cle] || c.largeur;

  t.entete = () => {
    const table = $(selecteur);
    table.querySelector("colgroup")?.remove();
    table.prepend(el("colgroup", {}, colonnes.map((c) => el("col", { "data-col": c.cle, style: `width:${largeur(c)}px` }))));
    table.style.width = colonnes.reduce((s, c) => s + largeur(c), 0) + "px";
    const ths = colonnes.map((c) => {
      const actif = t.tri.cle === c.cle;
      const th = el("th", { class: [c.align || "", c.tri ? "triable" : "", actif ? "trie" : ""].join(" "), title: c.aide || (c.tri ? "Cliquer pour trier" : ""),
        "aria-sort": actif ? (t.tri.sens > 0 ? "ascending" : "descending") : null },
        el("span", { class: "libelle" }, c.titre),
        c.tri ? el("span", { class: "fleche" }, actif ? (t.tri.sens > 0 ? "▲" : "▼") : "↕") : null,
        el("span", { class: "poignee", title: "Glisser pour élargir · double-clic : largeur d'origine" }));
      if (c.tri) th.addEventListener("click", (e) => { if (!e.target.classList.contains("poignee")) trier(c.cle); });
      brancherPoignee(th.querySelector(".poignee"), c);
      return th;
    });
    table.querySelector("thead").replaceChildren(el("tr", {}, ths));
  };

  function trier(cle) {
    // 1er clic : croissant ; 2e : décroissant ; 3e : retour à l'ordre d'origine
    if (t.tri.cle !== cle) t.tri = { cle, sens: 1 };
    else if (t.tri.sens > 0) t.tri = { cle, sens: -1 };
    else t.tri = { cle: null, sens: 1 };
    memo.ecrire(memoCle + "-tri", t.tri);
    t.entete();
    rafraichir();
  }

  function brancherPoignee(poignee, c) {
    poignee.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      delete t.largeurs[c.cle];
      memo.ecrire(memoCle + "-largeurs", t.largeurs);
      t.entete();
    });
    poignee.addEventListener("mousedown", (e) => {
      e.preventDefault(); e.stopPropagation();
      const x0 = e.clientX, l0 = largeur(c);
      const table = $(selecteur);
      const col = table.querySelector(`col[data-col="${c.cle}"]`);
      const total0 = parseFloat(table.style.width);
      document.body.classList.add("redimension");
      const bouger = (ev) => {
        const l = Math.max(36, Math.round(l0 + ev.clientX - x0));
        col.style.width = l + "px";
        table.style.width = total0 - l0 + l + "px";
        t.largeurs[c.cle] = l;
      };
      const lacher = () => {
        document.removeEventListener("mousemove", bouger);
        document.removeEventListener("mouseup", lacher);
        document.body.classList.remove("redimension");
        memo.ecrire(memoCle + "-largeurs", t.largeurs);
      };
      document.addEventListener("mousemove", bouger);
      document.addEventListener("mouseup", lacher);
    });
  }

  /** Les éléments dans l'ordre du tri choisi (ordre d'origine à égalité, ou sans tri). */
  t.trier = (elements) => {
    const c = colonnes.find((x) => x.cle === t.tri.cle);
    if (!c) return elements;
    const ordre = new Map(elements.map((x, i) => [x, i]));
    const cmp = (a, b) => (typeof a === "string" ? a.localeCompare(b, "fr", { numeric: true }) : a - b);
    return [...elements].sort((a, b) => cmp(c.tri(a), c.tri(b)) * t.tri.sens || ordre.get(a) - ordre.get(b));
  };
  return t;
}

const tableDecompte = tableTriable({ selecteur: "table.decompte", colonnes: COLONNES, memoCle: "compta", rafraichir: () => rendreLignes() });

function rendreLignes() {
  $("#lignes").replaceChildren(...tableDecompte.trier(etat.donnees.lignes.filter(visible)).map(rendreLigne));
  verrouiller($("#lignes"));
  $("#vide").hidden = etat.donnees.lignes.length > 0;
}

function optionsCotation(actuelle) {
  const liste = [...etat.general.cotations];
  if (actuelle && !liste.includes(actuelle)) liste.push(actuelle);
  return [el("option", { value: "" }, "—"), ...liste.map((c) => el("option", { value: c, selected: c === actuelle }, c))];
}

function rendreLigne(l) {
  const ch = (champ, valeur) => modifier(l.id, { [champ]: valeur });
  return el("tr", { "data-id": l.id, class: [l.fse ? "" : "manuelle", l.pointee ? "pointee" : ""].join(" ") },
    COLONNES.map((c) => el("td", {
      class: [c.align || "", c.calc ? "calc" : "", c.classe ? c.classe(l) : "", "c-" + c.cle].join(" "),
      title: c.titreCellule ? c.titreCellule(l) : null,
    }, c.cellule(l, ch))));
}

async function modifier(id, champs) {
  const actif = document.activeElement;
  const focus = actif && actif.closest("tr") ? [actif.closest("tr").dataset.id, actif.dataset.champ] : null;
  try {
    etat.donnees = await api("PUT", `/api/mois/${etat.mois}/ligne/${id}`, champs);
  } catch (e) { toast(e.message); }
  if (!etat.donnees.lignes.some((l) => l.id === id)) toast("Ligne déplacée dans son nouveau mois.");
  rendreRecap();
  if (etat.donnees.reevaluees) {
    // La validation a appris quelque chose à l'outil : d'autres lignes ont été mises à jour.
    toast(`Merci ! ${etat.donnees.reevaluees} autre(s) ligne(s) à vérifier mise(s) à jour grâce à cette validation.`, 5000);
    rendreLignes();
  }
  const l = etat.donnees.lignes.find((x) => x.id === id);
  const ancienne = $(`#lignes tr[data-id="${CSS.escape(id)}"]`);
  if (ancienne) {
    if (l && visible(l)) ancienne.replaceWith(rendreLigne(l)); else ancienne.remove();
  }
  if (focus) {
    const cible = $(`#lignes tr[data-id="${CSS.escape(focus[0])}"] [data-champ="${focus[1]}"]`);
    if (cible && cible !== document.activeElement) cible.focus();
  }
}

/** Pointer (ou dépointer) une ligne ; avertit si elle ne retrouve pas Ingenus ou n'a pas de cotation. */
async function pointer(l, caseACocher) {
  if (!caseACocher.checked) return modifier(l.id, { statut: "depointee" });
  const soucis = [];
  if (!l.cotation) soucis.push("elle n'a pas de cotation");
  if (l.calcul.ok_total === false) soucis.push(`son total (${euros(l.calcul.total)}) ne correspond pas à Ingenus (${euros(l.montant_ingenus)})`);
  else if (l.calcul.controle === "à vérifier") soucis.push("la part patiente ne correspond pas à Ingenus");
  if (soucis.length && !confirm(`Attention : ${soucis.join(" et ")}.\n\nPointer quand même cette ligne (${l.patiente || "sans nom"}, ${l.date}) ?`)) {
    caseACocher.checked = false;
    return;
  }
  return modifier(l.id, { statut: "" });
}

async function ajouter() {
  try {
    etat.donnees = await api("POST", `/api/mois/${etat.mois}/ligne`, {});
    etat.filtre = "tout"; etat.recherche = ""; $("#recherche").value = "";
    majFiltres();
    rendreRecap(); rendreLignes();
    const tr = $(`#lignes tr[data-id="${CSS.escape(etat.donnees.nouvelle)}"]`);
    if (tr) { tr.scrollIntoView({ block: "center" }); tr.querySelector('[data-champ="date"]').focus(); }
    if (!etat.general.mois.includes(etat.mois)) etat.general.mois.push(etat.mois);
  } catch (e) { toast(e.message); }
}

async function supprimer(l) {
  if (!confirm(`Supprimer l'ajout manuel « ${l.patiente || "sans nom"} » du ${l.date} ?`)) return;
  try {
    etat.donnees = await api("DELETE", `/api/mois/${etat.mois}/ligne/${l.id}`);
    rendreRecap(); rendreLignes();
  } catch (e) { toast(e.message); }
}

function majFiltres() {
  document.querySelectorAll("[data-filtre]").forEach((b) => b.classList.toggle("actif", b.dataset.filtre === etat.filtre));
}

// ------------------------------------------------------------------ imports

async function importer(fichiers) {
  if (!fichiers.length) return;
  const messages = [];
  let dernier = null;
  for (const f of fichiers) {
    try {
      const r = await api("POST", "/api/import", await f.arrayBuffer(), { "X-Nom-Fichier": encodeURIComponent(f.name) });
      etat.general.mois = r.mois;
      if (r.ignorees) messages.push(`${r.ignorees} FSE antérieures au début de la compta (${libelleMois(r.debut)}) ignorées`);
      for (const b of r.bilans) {
        if (b.hors_cloture) {
          messages.push(`${libelleMois(b.mois)} est clôturé : ${b.hors_cloture} FSE non intégrée(s), rouvre le mois pour les ajouter`);
          continue;
        }
        messages.push(`${libelleMois(b.mois)} : ${b.nouvelles} FSE ajoutées, ${b.mises_a_jour} mises à jour` +
          (b.a_verifier ? `, ${b.a_verifier} à vérifier` : ""));
        dernier = b.mois;
      }
    } catch (e) { messages.push(`${f.name} : ${e.message}`); }
  }
  toast(messages.length ? messages.join("\n") : "Rien de nouveau : ces FSE étaient déjà intégrées.", 7000);
  await chargerMois(dernier || etat.mois);
}

// ------------------------------------------------------------------ PDF (impression du navigateur)

function imprimer() {
  const d = etat.donnees, r = d.recap;
  const ligneRecap = (t, v) => el("div", {}, el("span", {}, t), el("strong", {}, v));
  const entetes = ["Date", "Patiente", "Cotation", "F", "P", "km", "Mode", "Acte", "Frais", "Total", "Ingenus", "Contrôle", "N° FSE"];
  const corps = d.lignes.map((l) => el("tr", {},
    el("td", {}, l.date.split("-").reverse().join("/")), el("td", {}, l.patiente), el("td", {}, l.cotation),
    el("td", {}, l.ferie ? "✓" : ""), el("td", {}, l.precoce ? "✓" : ""), el("td", {}, l.km ?? ""),
    el("td", {}, l.mode), el("td", { class: "n" }, nb(l.calcul.acte)), el("td", { class: "n" }, nb(l.calcul.frais)),
    el("td", { class: "n" }, nb(l.calcul.total)), el("td", { class: "n" }, nb(l.montant_ingenus)),
    el("td", { class: l.calcul.controle === "à vérifier" ? "ko" : "" }, l.calcul.controle), el("td", {}, l.fse)));
  $("#impression").replaceChildren(
    el("h1", {}, `Décompte — ${libelleMois(d.mois)}` + (d.cloture ? ` (clôturé le ${d.cloture.split("-").reverse().join("/")})` : "")),
    el("div", { class: "recap-imp" },
      ligneRecap("Total actes", euros(r.total_actes)), ligneRecap("Total frais", euros(r.total_frais)),
      ligneRecap("Titulaire (seule)", euros(r.titulaire_seule)), ligneRecap("Total Ingenus (FSE)", euros(r.total_ingenus)),
      ligneRecap(`Titulaire remplacée (${Math.round(r.taux_retrocession * 100)} %)`, euros(r.titulaire_remplacee)),
      ligneRecap("Remplaçant", euros(r.remplacant)),
      ligneRecap("Lignes / ajouts manuels", `${r.nb_lignes} / ${r.ajouts_manuels}`),
      ligneRecap("Écarts avec Ingenus", String(r.ecarts_ingenus))),
    el("table", {}, el("thead", {}, el("tr", {}, entetes.map((h) => el("th", {}, h)))), el("tbody", {}, corps)),
  );
  const titre = document.title;
  document.title = `Décompte ${d.mois}`; // nom proposé pour le PDF
  window.print();
  document.title = titre;
}

// ------------------------------------------------------------------ tarifs

async function chargerTarifs() {
  etat.tarifs = await api("GET", "/api/tarifs");
  rendreTarifs();
}

function champ(obj, cle, attrs = {}) {
  return el("input", Object.assign({ type: "text", value: obj[cle] ?? "", oninput: (e) => { obj[cle] = e.target.value; } }, attrs));
}

const num = (v) => parseFloat(String(v ?? "").replace(",", ".")) || 0;
const COLONNES_ACTES = [
  { cle: "cotation", titre: "Cotation", largeur: 130, tri: (a) => String(a.cotation ?? ""),
    cellule: (a) => champ(a, "cotation") },
  { cle: "tarif", titre: "Tarif (€)", largeur: 100, align: "n", tri: (a) => num(a.tarif),
    cellule: (a) => champ(a, "tarif", { inputmode: "decimal" }) },
  { cle: "ferie", titre: "Férié (€)", largeur: 100, align: "n", tri: (a) => num(a.ferie),
    cellule: (a) => champ(a, "ferie", { inputmode: "decimal" }) },
  { cle: "precoce", titre: "Précoce (€)", largeur: 110, align: "n", tri: (a) => num(a.precoce),
    cellule: (a) => champ(a, "precoce", { inputmode: "decimal" }) },
  { cle: "tiers_payant", titre: "Tiers payant", largeur: 110, align: "c", tri: (a) => (a.tiers_payant ? 1 : 0),
    cellule: (a) => el("input", { type: "checkbox", checked: a.tiers_payant, onchange: (e) => { a.tiers_payant = e.target.checked; } }) },
  { cle: "actions", titre: "", largeur: 48, align: "c",
    cellule: (a) => el("button", { class: "icone", title: "Supprimer", onclick: () => {
      etat.tarifs.actes.splice(etat.tarifs.actes.indexOf(a), 1); rendreTarifs(); } }, "🗑") },
];
const tableActes = tableTriable({ selecteur: "table.actes", colonnes: COLONNES_ACTES, memoCle: "compta-actes", rafraichir: () => rendreTarifs() });

function rendreTarifs() {
  const t = etat.tarifs;
  $("#tarifs-actes").replaceChildren(...tableActes.trier(t.actes).map((a) => el("tr", {},
    COLONNES_ACTES.map((c) => el("td", { class: c.align || "" }, c.cellule(a))))));
  const noms = { ik: "IK (€ par km)", md: "MD (€)", part_patiente: "Part patiente en tiers payant (0,3 = 30 %)",
    retrocession: "Taux de rétrocession (0,25 = 25 %)" };
  $("#tarifs-params").replaceChildren(...Object.entries(noms).map(([k, v]) => el("tr", {},
    el("td", {}, v), el("td", { class: "n" }, champ(t.parametres, k, { inputmode: "decimal" })))));
}

async function enregistrerTarifs() {
  try {
    etat.tarifs = await api("PUT", "/api/tarifs", etat.tarifs);
    etat.general = await api("GET", "/api/etat");
    rendreTarifs();
    const t = etat.tarifs;
    toast("Tarifs enregistrés."
      + (t.renommees ? ` ${t.renommees} ligne(s) des mois non clôturés renommée(s).` : "")
      + (t.reevaluees ? ` ${t.reevaluees} ligne(s) à vérifier mise(s) à jour.` : ""), 6000);
  } catch (e) { toast(e.message, 8000); }
}

function changerVue(vue) {
  document.querySelectorAll("[data-vue]").forEach((b) => b.classList.toggle("actif", b.dataset.vue === vue));
  $("#vue-decompte").hidden = vue !== "decompte";
  $("#vue-tarifs").hidden = vue !== "tarifs";
  if (vue === "tarifs") chargerTarifs(); else chargerMois(etat.mois);
}

// ------------------------------------------------------------------ mise à jour de l'app

function afficherMaj() {
  const m = etat.general.maj, b = $("#bandeau-maj");
  if (!m || !etat.general.app) { b.hidden = true; return; }
  b.replaceChildren(
    el("span", {}, `Une nouvelle version de Compta pro est disponible : ${m.version} (installée : ${etat.general.version}).`),
    el("button", { onclick: installerMaj }, "Installer et redémarrer"));
  b.hidden = false;
}

async function installerMaj() {
  const b = $("#bandeau-maj");
  b.replaceChildren(el("span", {}, "Téléchargement de la mise à jour…"));
  try {
    await api("POST", "/api/mise-a-jour");
    b.replaceChildren(el("span", {}, "Compta pro redémarre : une nouvelle page va s'ouvrir, tu peux fermer celle-ci."));
  } catch (e) { b.replaceChildren(el("span", {}, "Mise à jour impossible : " + e.message)); }
}

// ------------------------------------------------------------------ démarrage

async function demarrer() {
  etat.general = await api("GET", "/api/etat");
  $("#pied").replaceChildren(`Compta pro ${etat.general.version} · données : ${etat.general.donnees} · `,
    el("a", { href: "https://github.com/Sinjonathan/compta-pro#readme", target: "_blank", rel: "noopener" }, "Mode d'emploi"));
  afficherMaj();
  // L'app vérifie sur GitHub au lancement puis toutes les 12 h ; la page lui redemande le résultat
  // peu après l'ouverture, quand on revient sur l'onglet, et toutes les heures (appel local).
  const rafraichirMaj = async () => {
    try { etat.general.maj = (await api("GET", "/api/etat")).maj; afficherMaj(); } catch (e) { /* app fermée */ }
  };
  setTimeout(rafraichirMaj, 8000);
  setInterval(rafraichirMaj, 3600 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) rafraichirMaj(); });
  let mois = null;
  try { mois = localStorage.getItem("compta-mois"); } catch (e) { /* rien */ }
  if (!mois) mois = etat.general.mois.at(-1) || etat.general.aujourdhui.slice(0, 7);

  $("#mois").addEventListener("change", (e) => e.target.value && chargerMois(e.target.value));
  document.querySelectorAll("[data-vue]").forEach((b) => b.addEventListener("click", () => changerVue(b.dataset.vue)));
  document.querySelectorAll("[data-filtre]").forEach((b) => b.addEventListener("click", () => {
    etat.filtre = b.dataset.filtre; majFiltres(); rendreLignes();
  }));
  $("#recherche").addEventListener("input", (e) => { etat.recherche = e.target.value.trim(); rendreLignes(); });
  $("#btn-ajout").addEventListener("click", ajouter);
  $("#btn-import").addEventListener("click", () => $("#fichiers").click());
  $("#fichiers").addEventListener("change", (e) => { importer([...e.target.files]); e.target.value = ""; });
  $("#btn-pdf").addEventListener("click", imprimer);
  $("#btn-tarifs").addEventListener("click", enregistrerTarifs);
  $("#btn-ajout-acte").addEventListener("click", () => {
    etat.tarifs.actes.push({ cotation: "", ancien: "", tarif: "", ferie: 21, precoce: 25, tiers_payant: false }); rendreTarifs();
  });
  $("#btn-cloture").addEventListener("click", basculerCloture);

  // Glisser-déposer des exports sur toute la fenêtre
  let profondeur = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); profondeur++; $("#depot").hidden = false; });
  window.addEventListener("dragleave", () => { if (--profondeur <= 0) { profondeur = 0; $("#depot").hidden = true; } });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault(); profondeur = 0; $("#depot").hidden = true;
    importer([...e.dataTransfer.files].filter((f) => /\.csv$/i.test(f.name)));
  });

  tableDecompte.entete();
  tableActes.entete();
  await chargerMois(mois);
}

demarrer().catch((e) => toast("Impossible de démarrer : " + e.message, 10000));
