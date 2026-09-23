"""Résolution adaptative d'un champ — dernier recours de `locate_field` (« Chantier F », F.2/F.3).

⚠️ **Jamais le premier essai.** La cascade déterministe de `locate_field` (name → data-test(id) →
classe CSS → libellé → placeholder — doc officielle Playwright/Testing Library, alignée en
2026-09-14) reste TOUJOURS tentée en premier : gratuite, rapide, sans appel réseau. Ce module n'agit
que lorsqu'elle a TOUT épuisé sans rien trouver.

**Principe (Playwright MCP, "Self-Healing Test Automation: Beyond Locator Patching" — Keysight) :**
au lieu de faire deviner un sélecteur CSS à un modèle qui n'a jamais vu la vraie page, on lui montre
l'état RÉEL — la liste des éléments interactifs effectivement présents (rôle + nom accessible,
JAMAIS une image) — et on lui demande de CHOISIR un élément parmi ceux qui existent, ou de dire
qu'aucun ne correspond. Jamais inventer un élément absent de la liste : élire, ou échouer
honnêtement (`idx=null`), exactement comme `select_option_strict` refuse déjà d'inventer une option.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Attribut temporaire posé sur chaque candidat pour le retrouver après le choix du modèle — même
# esprit que les `ref_N` de Playwright MCP, sans dépendre de son protocole.
_ATTR_MARQUEUR = "data-tp-adaptive-idx"

# Best-effort : un plafond de candidats borne la taille du prompt (coût) ET le temps du JS. 200
# éléments interactifs sur un même écran est déjà un signe d'écran anormalement chargé.
_MAX_CANDIDATS = 200

_JS_CANDIDATS = """(args) => {
    const [attr, max] = args;
    const selecteur = 'input, select, textarea, button, a, [role], [tabindex]';
    const elements = Array.from(document.querySelectorAll(selecteur))
        .filter(el => el.offsetParent !== null || el.getClientRects().length > 0)
        .slice(0, max);
    return elements.map((el, i) => {
        el.setAttribute(attr, String(i));
        const label = el.labels && el.labels.length ? el.labels[0].innerText : '';
        return {
            idx: i,
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            nom: (el.getAttribute('aria-label') || label || el.placeholder ||
                  el.innerText || el.value || el.name || '').trim().slice(0, 80),
            type: el.getAttribute('type') || '',
        };
    });
}"""

_JS_NETTOYAGE = """(attr) => {
    document.querySelectorAll(`[${attr}]`).forEach(el => el.removeAttribute(attr));
}"""

_SYSTEM = (
    "Tu choisis, parmi une liste d'éléments RÉELLEMENT présents sur une page web, celui qui "
    "correspond le mieux à une intention de test exprimée en langage naturel. Tu ne dois JAMAIS "
    "choisir un idx absent de la liste fournie, ni en inventer un. Si aucun élément ne correspond "
    "avec une confiance raisonnable, réponds idx=null plutôt que de deviner.\n\n"
    "En plus de choisir, indique si l'élément choisi ressemble à un MENU ou un GROUPE générique "
    "(souvent un nom court et vague — ex. « Tickets », « Rapports » — qui pourrait révéler "
    "d'autres options en cliquant dessus, sans être lui-même la destination finale précise) "
    "plutôt qu'à une action ou un lien SPÉCIFIQUE menant directement à ce qui est demandé (ex. "
    "« Tous les tickets », « Nouveau rapport de ventes »). Mets `menu_parent_probable=true` si "
    "un doute raisonnable existe sur ce point, `false` si tu es confiant que c'est la destination."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "idx": {"type": ["integer", "null"]},
        "menu_parent_probable": {"type": "boolean"},
        "raison": {"type": "string"},
    },
    "required": ["idx", "menu_parent_probable", "raison"],
    "additionalProperties": False,
}


def _nettoyer_marqueurs(page) -> None:
    """Retire l'attribut temporaire posé par cette résolution — utilisé sur les chemins « aucune
    correspondance » (rien à réutiliser ensuite). Sur le chemin réussi, on NE nettoie PAS : le
    `Locator` rendu ré-exécute son sélecteur à chaque action (paresseux), retirer l'attribut avant
    que l'appelant agisse casserait la résolution qu'on vient de faire. Une poignée d'attributs
    `data-tp-adaptive-idx` oubliés en fin de scénario est un coût négligeable, jamais fonctionnel
    (l'index est réécrit à chaque nouvel appel, aucun risque de faux positif futur). Best-effort,
    jamais lève.
    """
    try:
        page.evaluate(_JS_NETTOYAGE, _ATTR_MARQUEUR)
    except Exception:
        pass


def _candidats_reels(page) -> list[dict]:
    try:
        return page.evaluate(_JS_CANDIDATS, [_ATTR_MARQUEUR, _MAX_CANDIDATS]) or []
    except Exception as exc:
        logger.warning("[adaptatif] instantané d'accessibilité impossible (%s)", type(exc).__name__)
        return []


def _choisir_element(intention: str, ident: str, valeur: str, candidats: list[dict], *,
                     llm=None, cost_tracker=None) -> tuple[int, bool] | None:
    """Un SEUL appel à un modèle rapide : intention + valeur + éléments réels → (idx, est un
    menu/groupe plutôt qu'une destination finale ?), ou rien.

    Import différé de `testpilot` : cette bibliothèque doit s'importer à la collecte (dry-run) sans
    exiger le paquet applicatif complet — même garde que `_route_courante` ci-contre.
    """
    from testpilot import config
    from testpilot.llm.adapter import LLMAdapter

    moteur = llm or LLMAdapter()
    user = (
        f"Intention du test (texte du step) : {intention!r}\n"
        f"Identifiant technique recherché (peut être obsolète ou renommé) : {ident!r}\n"
        + (f"Valeur à saisir : {valeur!r}\n" if valeur else "")
        + "Éléments RÉELLEMENT présents sur la page (idx, rôle, nom accessible, type) :\n"
        + json.dumps(candidats, ensure_ascii=False)
    )
    data = moteur.call_json(system_prompt=_SYSTEM, user_content=user, schema=_SCHEMA,
                            model=config.MODEL_FAST, cost_tracker=cost_tracker,
                            label="resolution_adaptative")
    idx = data.get("idx") if isinstance(data, dict) else None
    if not isinstance(idx, int):
        return None
    if idx not in {c["idx"] for c in candidats}:
        return None  # le modèle a désigné un idx hors liste : jamais suivi (principe F.2)
    return idx, bool(data.get("menu_parent_probable", False))


def resoudre_champ_adaptatif(page, ident: str, intention: str, *, valeur: str = "", llm=None,
                             cost_tracker=None):
    """Dernier recours de `locate_field` : montre les éléments RÉELS de la page à un modèle rapide,
    qui CHOISIT parmi eux (ou dit qu'aucun ne convient) — ne devine jamais un sélecteur CSS.

    Rend un `Locator` pointant l'élément élu, ou `None` si rien n'a pu être résolu avec confiance.
    **Jamais d'exception d'ici** : à l'appelant de décider comment échouer, exactement comme il le
    fait déjà quand `locate_field` rend un `Locator` vide après tous ses paliers déterministes.

    ⚠️ Sans `intention` (step non instrumenté, ou appelé hors d'un step Behave), rend `None`
    immédiatement — aucune tentative aveugle, zéro appel LLM, zéro coût.

    ⚠️ **`logger.warning` seul ne suffit JAMAIS à rendre un échec visible** (même défaut que
    documenté pour `_record_field_fallback` dans `_base_helpers.py` : Behave capture le logging en
    mémoire par scénario et ne le recrache sur AUCUN format JSON custom — un `--logcapture`
    silencieux, mesuré en run réel le 2026-09-22, qui avait rendu ce palier totalement muet même
    sur un vrai échec). Le diagnostic est donc AUSSI posé sur `page._tp_dernier_diagnostic_adaptatif`
    (même patron que `_tp_intention_step`) — c'est ce que `_repli_adaptatif` (`_base_helpers.py`)
    relit et route vers le sidecar `_record_field_fallback`, TOUJOURS, succès ou échec.

    ⚠️ **`page._tp_dernier_choix_menu_parent`, posé sur un succès** (« Chantier F », navigation à
    plusieurs niveaux, bug RÉEL mesuré en run, Sapian, 2026-09-22, cas C127) : un signal DOM
    (comparer le nombre/recouvrement de candidats avant/après clic) s'était révélé peu fiable —
    l'interface commune d'Odoo (barre d'outils, filtres, pagination) domine le nombre de candidats
    sur TOUTES les vues, peu importe le seuil choisi, rendant le recouvrement peu discriminant.
    On demande donc DIRECTEMENT au modèle — qui a déjà vu la liste complète des candidats — s'il
    pense avoir choisi un MENU/GROUPE générique (nom court, pourrait révéler d'autres options en
    cliquant dessus) plutôt qu'une destination finale précise. `navigate_menu` relit ce booléen
    pour décider de reboucler sur le même segment plutôt que de se fier à l'URL seule.
    """
    if not intention:
        return None
    candidats = _candidats_reels(page)
    if not candidats:
        message = (f"aucun élément interactif visible sur {getattr(page, 'url', '?')} — rien à "
                   f"proposer au modèle")
        logger.warning("[adaptatif] '%s' : %s", ident, message)
        page._tp_dernier_diagnostic_adaptatif = message
        return None
    try:
        choix = _choisir_element(intention, ident, valeur, candidats, llm=llm,
                                 cost_tracker=cost_tracker)
    except Exception as exc:
        message = f"appel modèle impossible ({type(exc).__name__}: {exc})"
        logger.warning("[adaptatif] '%s' : %s", ident, message)
        page._tp_dernier_diagnostic_adaptatif = message
        _nettoyer_marqueurs(page)
        return None
    if choix is None:
        message = (f"le modèle n'a trouvé aucune correspondance fiable parmi "
                   f"{len(candidats)} élément(s) réel(s) — candidats : "
                   f"{[c.get('nom') or c.get('role') for c in candidats][:15]}")
        logger.warning("[adaptatif] '%s' : %s", ident, message)
        page._tp_dernier_diagnostic_adaptatif = message
        _nettoyer_marqueurs(page)
        return None
    idx, menu_parent_probable = choix
    loc = page.locator(f'[{_ATTR_MARQUEUR}="{idx}"]')
    if loc.count() == 0:
        message = f"idx={idx} choisi par le modèle mais introuvable après coup"
        logger.warning("[adaptatif] '%s' : %s", ident, message)
        page._tp_dernier_diagnostic_adaptatif = message
        _nettoyer_marqueurs(page)
        return None
    page._tp_dernier_diagnostic_adaptatif = (
        f"résolu — élément #{idx} choisi parmi {len(candidats)} candidat(s)"
        + (" (menu/groupe probable, pas forcément la destination finale)"
           if menu_parent_probable else ""))
    page._tp_dernier_choix_menu_parent = menu_parent_probable
    # Le libellé RÉEL affiché par l'élément élu (Lot 2, 2026-09-23) — `navigate_menu` le relit
    # pour apprendre, projet par projet, quel libellé a VRAIMENT permis de franchir ce segment,
    # quand `ident` (le segment cherché) ne correspondait à rien tel quel (langue différente,
    # sous-menu renommé…). Vide si l'élément élu n'a aucun nom accessible — rien à apprendre.
    page._tp_dernier_libelle_choisi = next(
        (c.get("nom", "") for c in candidats if c.get("idx") == idx), "")
    return loc.first
