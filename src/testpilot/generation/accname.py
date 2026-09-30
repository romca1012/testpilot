"""Calcul du rôle + nom accessible d'un élément cliqué — sous-lot A du lot « Enregistrement
assisté du chemin de connexion » (2026-09-29).

⚠️ **Aucun modèle de langage dans ce module, jamais.** Le calcul est un algorithme déterministe :
même page, même clic → même résultat, à chaque fois. C'est la contrainte non négociable du lot.

⚠️ **Deux algorithmes bien distincts, sans confusion possible** :
1. La remontée d'arbre — depuis un POINT (x, y) cliqué, retrouver le premier élément ancêtre (ou
   l'élément lui-même) porteur d'un rôle ARIA « interactif exploitable ». Ce n'est PAS couvert par
   la norme AccName (qui part toujours d'un élément déjà identifié, jamais d'un point) : c'est une
   règle propre à ce projet, sans jeu de tests officiel externe pour la prouver — d'où des tests
   volontairement généreux sur ses cas limites (voir `tests/test_accname.py`).
2. Le calcul du nom accessible d'un élément déjà identifié — l'algorithme W3C « Accessible Name
   and Description Computation » (AccName), lu sur la source du groupe de travail (voir README de
   ce lot / rapport de fin de sous-lot pour la référence exacte et les cas écartés), PAS travaillé
   de mémoire.

Tout tourne en JavaScript évalué dans la page réelle (`page.evaluate`) — même motif déjà établi
dans ce dépôt pour lire le DOM (`scripts/crawl_domaine.py::_inspecter_page`) : le calcul a besoin
de l'état RÉEL du DOM au moment du clic (attributs ARIA, visibilité calculée), que Python ne peut
lire qu'en repassant par le navigateur de toute façon.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class ElementIntrouvableError(Exception):
    """Même famille que `behave_runtime/steps_library/_base_helpers.py::ElementIntrouvableError`
    (dupliqué ici : ce module vit dans `src/testpilot`, hors de la bibliothèque de steps à plat,
    même raison que les autres duplications déjà documentées dans ce dépôt entre les deux mondes).

    Levée UNIQUEMENT quand une cible réelle a été trouvée mais que son rôle+nom ne suffirait pas à
    la retrouver sans ambiguïté au rejeu (plusieurs éléments y répondraient) — jamais pour un clic
    qui ne touche rien d'interactif (voir `RoleNom.role is None` dans ce cas, une absence propre,
    pas une erreur : un simple clic égaré pendant la navigation ne doit jamais faire échouer toute
    une session d'enregistrement)."""


class RoleNom(TypedDict):
    role: Optional[str]
    name: str


# ── Rôles ARIA « interactifs exploitables » — où la remontée d'arbre s'arrête ────────────────────
# Rôles de widget de la spec WAI-ARIA (https://www.w3.org/TR/wai-aria-1.2/#widget_roles) utiles à
# un chemin de connexion : on exclut délibérément les rôles structurels (generic, group, region,
# presentation, none, document...) qui ne doivent JAMAIS arrêter la remontée — un clic sur un
# `<div>` de mise en page doit continuer à chercher un ancêtre réellement actionnable.
_ROLES_INTERACTIFS = frozenset({
    "button", "link", "checkbox", "radio", "textbox", "combobox", "listbox", "option",
    "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "switch", "slider", "spinbutton",
    "searchbox",
})

# Rôle ARIA implicite des éléments HTML natifs les plus courants (table partielle, volontairement
# limitée à ce qui compte pour un formulaire de connexion — pas une réimplémentation complète de
# la table HTML-AAM). Un attribut `role="..."` explicite prime TOUJOURS sur cette table.
_ROLE_IMPLICITE_JS = r"""
function roleImplicite(el) {
  const tag = el.tagName.toLowerCase();
  // `summary` retiré (revue verdict-reviewer chantier-entier, 2026-09-30) : vérifié avec un vrai
  // Chromium (`page.locator(...).aria_snapshot()`), Playwright expose `<summary>` avec le rôle
  // `group`, jamais `button` — un `<summary>` classé `button` ici aurait été capturé « avec
  // succès » mais introuvable par `page.get_by_role('button', ...)` au rejeu (sous-lot D), levant
  // à tort `SequenceConnexionObsoleteError` sur une application qui n'a pourtant pas changé.
  if (tag === 'button') return 'button';
  if (tag === 'a' && el.hasAttribute('href')) return 'link';
  if (tag === 'textarea') return 'textbox';
  if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
  if (tag === 'option') return 'option';
  if (tag === 'input') {
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (type === 'checkbox') return 'checkbox';
    if (type === 'radio') return 'radio';
    if (type === 'range') return 'slider';
    if (type === 'button' || type === 'submit' || type === 'reset' || type === 'image') return 'button';
    if (type === 'search') return 'searchbox';
    if (['text', 'email', 'password', 'tel', 'url'].includes(type)) return 'textbox';
    return null;
  }
  return null;
}
"""

# ── Remontée d'arbre : point cliqué → élément interactif exploitable, ou rien ────────────────────
# ⚠️ **Shadow DOM (ouvert) traversé explicitement** — bug mesuré en revue verdict-reviewer
# (2026-09-29, vrai Chromium) : `document.elementFromPoint` ne rend que l'hôte d'une racine shadow
# ouverte, jamais l'élément interne réellement sous le point cliqué. Sans ce perçage, un clic sur
# un bouton À L'INTÉRIEUR d'un composant (design system, widget d'authentification tiers — motif
# courant sur un écran de connexion) donnait soit une absence (`None`) pour un clic qui touchait
# pourtant une vraie cible, soit — pire — remontait sur un ANCÊTRE hors du shadow DOM avec un
# rôle+nom qui ne correspondait pas à ce qui avait été cliqué (un résultat FAUX, plausible,
# indiscernable d'une capture correcte). Une racine FERMÉE reste invisible par construction du web
# (`el.shadowRoot` rend `null`) — limite du navigateur, pas de ce code, non contournable.
_RESOUDRE_CIBLE_JS = _ROLE_IMPLICITE_JS + r"""
function roleDe(el) {
  const explicite = el.getAttribute && el.getAttribute('role');
  return explicite || roleImplicite(el);
}

function elementSousLePoint(x, y) {
  let el = document.elementFromPoint(x, y);
  while (el && el.shadowRoot) {
    const interne = el.shadowRoot.elementFromPoint(x, y);
    if (!interne || interne === el) break;
    el = interne;
  }
  return el;
}

function parentOuHote(el) {
  const parent = el.parentElement;
  if (parent) return parent;
  const racine = el.getRootNode();
  return (racine instanceof ShadowRoot) ? racine.host : null;
}

function resoudreCible(x, y) {
  let el = elementSousLePoint(x, y);
  while (el && el !== document.documentElement) {
    const role = roleDe(el);
    if (role && ROLES_INTERACTIFS.includes(role)) {
      return { element: el, role };
    }
    el = parentOuHote(el);
  }
  return null;
}

// Tous les éléments du document, en perçant récursivement chaque racine shadow OUVERTE — pour le
// décompte d'homonymes (une racine fermée reste invisible, même limite que ci-dessus).
function tousLesElements(racine) {
  const resultat = [];
  for (const el of racine.querySelectorAll('*')) {
    resultat.push(el);
    if (el.shadowRoot) resultat.push(...tousLesElements(el.shadowRoot));
  }
  return resultat;
}
"""


def _js_avec_roles(gabarit: str) -> str:
    """Injecte la liste Python des rôles interactifs dans le gabarit JS — une seule source de
    vérité (`_ROLES_INTERACTIFS`), jamais dupliquée à la main côté JavaScript."""
    liste_js = "[" + ",".join(f"'{r}'" for r in sorted(_ROLES_INTERACTIFS)) + "]"
    return f"const ROLES_INTERACTIFS = {liste_js};\n" + gabarit


# ── Calcul du nom accessible (AccName) — élément déjà identifié ──────────────────────────────────
# Ordre EXACT vérifié sur la source du groupe de travail W3C (étapes 2B/2D/2E/2F/2I de l'algorithme
# « Text Alternative Computation » — la numérotation et l'ordre relatif sont ceux de la spec, pas
# une reconstruction de mémoire) :
#   2B aria-labelledby  >  2D aria-label  >  2E étiquette du langage hôte (label/alt)  >
#   2F/2G/2H nom depuis le contenu (texte visible, récursif)  >  2I `title`  >  `placeholder` en
#   tout dernier recours, restreint aux champs de saisie sans autre étiquette (HTML-AAM, pas
#   l'AccName pur).
# ⚠️ **`placeholder` déplacé APRÈS `title`** (revue verdict-reviewer chantier-entier, 2026-09-30) —
# vérifié avec un vrai Chromium : pour un champ portant À LA FOIS `title` ET `placeholder`,
# Playwright résout le nom accessible au `title` (son propre algorithme, utilisé au rejeu par
# `page.get_by_role`, sous-lot D), jamais au `placeholder`. L'ordre précédent (placeholder avant
# title) faisait calculer À LA CAPTURE un nom que le REJEU ne retrouvait jamais — une séquence
# confirmée avec succès devenait définitivement injouable, avec un message trompeur (« l'application
# a changé ») alors que c'est ce module qui se contredisait lui-même entre capture et rejeu.
# Étape 2C (« embedded control ») délibérément ÉCARTÉE : cas étroit (un `<label>` habillant un
# curseur de plage dont on inclurait la valeur courante), sans usage pour un chemin de connexion,
# documenté comme écart plutôt que traité en silence. `legend`/`caption` (fieldset/table) écartés
# pour la même raison : aucun rôle interactif de la table ci-dessus ne résout jamais vers ces
# éléments — du code jamais atteignable par `calculer()`, donc jamais testé, donc retiré plutôt
# que laissé en silence.
# Uniquement l'intersection avec `_ROLES_INTERACTIFS` : c'est TOUJOURS le rôle de la cible
# résolue par `resoudreCible` qui est testé contre cet ensemble au premier appel (`calculer()`),
# jamais un rôle non interactif. `heading`/`cell`/`gridcell`/`columnheader`/`rowheader`/`term`
# (retirés en revue verdict-reviewer, 2026-09-29) étaient du code mort pour la même raison que
# `legend`/`caption` ci-dessus — jamais atteignables, donc jamais testés, donc retirés plutôt que
# laissés en silence.
_ROLES_NOM_DEPUIS_CONTENU = frozenset({
    "button", "link", "tab", "menuitem", "option", "switch", "checkbox", "radio",
})

_ACCNAME_JS = r"""
function estMasque(el) {
  if (!(el instanceof Element)) return false;
  const style = getComputedStyle(el);
  return style.display === 'none' || style.visibility === 'hidden'
      || el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true';
}

function normaliser(texte) {
  return (texte || '').replace(/\s+/g, ' ').trim();
}

function nomDepuisRefs(ids, dejaVus, racine) {
  // `racine` (ShadowRoot ou Document, jamais un Element) : `getElementById` est scopé, un id à
  // l'intérieur d'un shadow root est INTROUVABLE depuis `document` (isolation de scope d'id
  // propre à la plateforme, pas une supposition) — bug mesuré en revue verdict-reviewer,
  // 2026-09-29, avec un vrai Chromium : un aria-labelledby valide à l'intérieur d'un shadow DOM
  // échouait silencieusement, le calcul retombant sur le contenu (nom plausible mais FAUX).
  return ids.split(/\s+/).filter(Boolean).map(id => {
    const cible = racine.getElementById(id);
    if (!cible) return '';
    // `viaReference=true` : un nœud RÉFÉRENCÉ par aria-labelledby garde son texte même masqué
    // (exception explicite de l'étape 2A) — jamais le cas d'une simple récursion de contenu.
    return calculerNom(cible, dejaVus, { viaReference: true, dansContenu: true });
  }).filter(Boolean).join(' ');
}

function etiquetteLangageHote(el) {
  const tag = el.tagName.toLowerCase();
  if (tag === 'img' || tag === 'area') return el.getAttribute('alt') || '';
  if (tag === 'input' && (el.type === 'image')) return el.getAttribute('alt') || '';
  // <label for="id"> — TOUS ceux qui référencent cet id, concaténés dans l'ordre du document
  // (comp_host_language_label.html : « textfield label 1 textfield label 2 »).
  // ⚠️ **Un `<label for>` MASQUÉ contribue quand même son texte** — revu en revue verdict-reviewer
  // chantier-entier (2026-09-30) : le correctif du 2026-09-29 (exclure un `<label>` masqué,
  // conforme à l'algorithme AccName pur, étape 2A) faisait diverger la capture de ce que Playwright
  // résout RÉELLEMENT au rejeu — vérifié avec un vrai Chromium (`aria_snapshot`/`get_by_role`) :
  // pour `<label for="x" style="display:none">Texte</label><input id="x">`, Playwright inclut
  // « Texte » dans le nom accessible, exactement comme pour un nœud référencé par aria-labelledby
  // (2A ne l'exempte pas explicitement pour `<label for>`, mais c'est le comportement mesuré, pas
  // supposé). La capture doit prédire ce que le REJEU trouvera, jamais l'algorithme de spec pur
  // seul — but de ce module (voir docstring de tête). Un `<label>` ENGLOBANT masqué reste hors de
  // cause : son enfant masqué avec lui n'a alors plus de `bounding_box`, donc jamais cliquable.
  // Recherche scopée à `el.getRootNode()` (ShadowRoot ou Document), jamais à `document` : bug de
  // fond mesuré en revue du 2026-09-29, un <label for> à l'intérieur d'un shadow DOM était
  // introuvable depuis `document` et le nom retombait silencieusement à vide (même revue).
  // `CSS.escape` : un id contenant un guillemet casserait le sélecteur autrement (levée bruyante,
  // pas un faux positif, mais fragile sans raison — signalé par la même revue).
  if (el.id) {
    const racine = el.getRootNode();
    const refs = Array.from(racine.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`))
      .map(l => normaliser(l.textContent)).filter(Boolean);
    if (refs.length) return refs.join(' ');
  }
  // <label> englobant (élément wrappé directement dans un <label>) — même garde.
  const englobant = el.closest('label');
  if (englobant && !estMasque(englobant)) return normaliser(englobant.textContent);
  return '';
}

function nomDepuisContenu(el, dejaVus) {
  let resultat = '';
  for (const enfant of el.childNodes) {
    if (enfant.nodeType === Node.TEXT_NODE) {
      resultat += enfant.textContent;
    } else if (enfant.nodeType === Node.ELEMENT_NODE) {
      if (estMasque(enfant)) {
        // Un descendant masqué ne contribue RIEN — contrairement au nœud directement référencé
        // par aria-labelledby (2A ne l'exempte pas, lui) : pas de `viaReference` ici.
        continue;
      } else if (enfant.tagName.toLowerCase() === 'img') {
        resultat += (enfant.getAttribute('alt') || '');
      } else {
        resultat += calculerNom(enfant, dejaVus, { viaReference: false, dansContenu: true });
      }
    }
    resultat += ' ';
  }
  return normaliser(resultat);
}

function calculerNom(el, dejaVus, options) {
  const { viaReference, dansContenu } = options || {};
  if (!(el instanceof Element)) return '';
  if (dejaVus.has(el)) return '';  // anti-boucle (aria-labelledby circulaire)
  dejaVus = new Set(dejaVus);
  dejaVus.add(el);

  // 2A — masqué et non référencé : nom vide. Seule l'exception explicite de la spec s'applique
  // (nœud directement pointé par aria-labelledby) — jamais une simple récursion de contenu.
  if (!viaReference && estMasque(el)) return '';

  // 2B — aria-labelledby.
  const labelledby = el.getAttribute('aria-labelledby');
  if (labelledby) {
    const nom = nomDepuisRefs(labelledby, dejaVus, el.getRootNode());
    if (nom) return nom;
  }

  // 2D — aria-label.
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel && normaliser(ariaLabel)) return normaliser(ariaLabel);

  // 2E — étiquette du langage hôte (label/alt).
  const hote = etiquetteLangageHote(el);
  if (hote) return hote;

  // 2F/2G/2H — nom depuis le contenu (rôles qui l'autorisent, ou traversée déjà en mode contenu).
  const role = el.getAttribute('role') || ROLE_IMPLICITE_POUR_CONTENU(el);
  if (dansContenu || (role && ROLES_NOM_DEPUIS_CONTENU.includes(role))) {
    const nom = nomDepuisContenu(el, dejaVus);
    if (nom) return nom;
  }

  // 2I — `title`.
  const title = el.getAttribute('title');
  if (title && normaliser(title)) return normaliser(title);

  // Repli HTML-AAM (pas l'AccName pur) — `placeholder`, en tout dernier recours, seulement pour un
  // champ de saisie sans aucune autre étiquette (ni title inclus, voir plus haut).
  const tag = el.tagName.toLowerCase();
  if ((tag === 'input' || tag === 'textarea')) {
    const placeholder = el.getAttribute('placeholder');
    if (placeholder && normaliser(placeholder)) return normaliser(placeholder);
  }

  return '';
}
"""


def _js_accname_sans_roles() -> str:
    """Le calcul AccName seul (`roleImplicite` vient déjà de `_RESOUDRE_CIBLE_JS`, jamais redéfini
    deux fois dans le même script — une redéclaration de fonction est certes tolérée par le
    JavaScript non strict, mais autant n'en avoir qu'une seule source de vérité)."""
    roles_contenu_js = "[" + ",".join(f"'{r}'" for r in sorted(_ROLES_NOM_DEPUIS_CONTENU)) + "]"
    return (
        f"const ROLES_NOM_DEPUIS_CONTENU = {roles_contenu_js};\n"
        "function ROLE_IMPLICITE_POUR_CONTENU(el) { "
        "const t = el.tagName.toLowerCase(); "
        "if (t === 'h1'||t==='h2'||t==='h3'||t==='h4'||t==='h5'||t==='h6') return 'heading'; "
        "return roleImplicite(el); }\n"
        + _ACCNAME_JS
    )


# ⚠️ **Un seul script, une seule fonction de plus haut niveau.** Toutes les déclarations
# (rôles interactifs, rôle implicite, remontée d'arbre, AccName) vivent DANS le corps de cette
# fonction fléchée — jamais en instructions de plus haut niveau suivies d'une expression finale,
# forme ambiguë pour `page.evaluate` (Playwright traite une chaîne comme UNE fonction/expression,
# pas une suite d'instructions top-level).
_SCRIPT_COMPLET = r"""
({x, y}) => {
""" + _js_avec_roles(_RESOUDRE_CIBLE_JS) + _js_accname_sans_roles() + r"""
  const cible = resoudreCible(x, y);
  if (!cible) return null;
  const nom = calculerNom(cible.element, new Set(), {});
  const homonymes = tousLesElements(document)
    .filter(el => roleDe(el) === cible.role)
    .map(el => calculerNom(el, new Set(), {}))
    .filter(n => n === nom).length;
  return { role: cible.role, name: nom, homonymes };
}
"""


def calculer(page, x: float, y: float) -> RoleNom | None:
    """Le rôle + nom accessible de l'élément interactif sous le point `(x, y)`, ou `None` si aucun
    ancêtre n'est porteur d'un rôle interactif exploitable (clic égaré pendant la navigation — un
    NO-OP pour l'appelant, jamais une erreur : voir la docstring du module).

    Lève `ElementIntrouvableError` si le (rôle, nom) trouvé correspondrait, au rejeu, à PLUSIEURS
    éléments de la page actuelle — une ambiguïté réelle, jamais résolue en silence par « le
    premier trouvé » (même principe que `_base_helpers.py::_un_seul`). Un seul aller-retour navi-
    gateur : la remontée d'arbre, le calcul du nom et le décompte des homonymes tournent dans le
    même `page.evaluate`, jamais dupliqués entre JS et Python.
    """
    resultat = page.evaluate(_SCRIPT_COMPLET, {"x": x, "y": y})
    if resultat is None:
        return None

    role, nom, homonymes = resultat["role"], resultat["name"], resultat["homonymes"]
    if homonymes > 1:
        raise ElementIntrouvableError(
            f"rôle « {role} », nom « {nom} » est ambigu : {homonymes} éléments y répondraient au "
            "rejeu — le geste serait retrouvé sur la mauvaise cible sans erreur. Reprenez "
            "l'enregistrement avec un clic sur un élément qui se distingue seul.")

    return {"role": role, "name": nom}
