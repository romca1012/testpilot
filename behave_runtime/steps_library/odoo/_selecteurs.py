"""Vocabulaire ERP Odoo (lot 08a, C7) — détection de version, table de sélecteurs par version,
et deux helpers d'attente/URL qui s'appuient dessus.

⚠️ **Candidats NON VÉRIFIÉS SUR BANC RÉEL** (2026-09-28) : cet environnement cloud n'a ni démon
Docker ni instance Odoo réelle (`docker ps` échoue ici) pour relever le DOM effectif des trois
versions de D9 (16.0, 17.0, 18.0 Community) avant de les figer, comme l'exige le lot. Les
candidats ci-dessous reprennent, pour les clés que le lot documente explicitement, EXACTEMENT les
sélecteurs qu'il donne ; pour les autres, ils suivent les conventions DOM les plus documentées du
web client Odoo (classes `o_*` stables depuis plusieurs versions majeures), sans mesure directe.
**À vérifier par le porteur sur le banc réel** (`docker compose -f compose.banc.yml up -d` puis
`python scripts/banc_mesure.py`) avant de les considérer fiables pour la génération réelle — le
rapport du lot le signale explicitement.
"""

from __future__ import annotations

import re

_RE_VERSION = re.compile(r"(\d+)\.(\d+)")


def parser_version(version_brute: str | None) -> tuple[int, int] | None:
    """(majeur, mineur) depuis la chaîne de version du serveur Odoo (ex. `"17.0"`, `"17.0e"`,
    `"saas~17.4"`). `None` si illisible — jamais une exception : une version indétectable est un
    signal informatif (repli sur la version la plus récente connue, voir `selecteurs`), pas un
    motif d'arrêt du scénario."""
    if not version_brute:
        return None
    m = _RE_VERSION.search(version_brute)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


# Les trois versions supportées (D9, validée) — Community, avec données de démo.
_VERSIONS_D9: tuple[tuple[int, int], ...] = ((16, 0), (17, 0), (18, 0))

# Clé logique → {version: [sélecteurs candidats, dans l'ordre d'essai]}.
# Un candidat peut porter un gabarit `{...}` (ex. `{methode}` pour `bouton_action`), résolu par
# `selecteurs(..., **valeurs)`.
_TABLE: dict[str, dict[tuple[int, int], list[str]]] = {
    # Donné explicitement par le lot.
    "bouton_action": {
        v: ['.o_form_view button[name="{methode}"]'] for v in _VERSIONS_D9
    },
    "barre_etat_courante": {
        v: ['.o_statusbar_status [aria-checked="true"]',
            '.o_statusbar_status .o_arrow_button_current']
        for v in _VERSIONS_D9
    },
    "ligne_x2many_ajout": {
        v: [".o_field_x2many_list_row_add a"] for v in _VERSIONS_D9
    },
    "dialogue_bouton_principal": {
        v: [".modal .modal-footer .btn-primary"] for v in _VERSIONS_D9
    },
    "enregistrer": {
        v: [".o_form_button_save"] for v in _VERSIONS_D9
    },
    "indicateur_chargement": {
        v: [".o_loading_indicator"] for v in _VERSIONS_D9
    },
    # NON donné explicitement — conventions DOM documentées du web client Odoo, non vérifiées ici.
    "ligne_x2many_cellule": {
        v: [".o_field_x2many_list_row_add", ".o_data_row .o_data_cell"] for v in _VERSIONS_D9
    },
    "dialogue": {
        v: [".o_dialog .modal", ".o_dialog"] for v in _VERSIONS_D9
    },
    "notification_erreur": {
        # Même motif que `_base_helpers.validation_error_notification` (garde générique 2026-08-13).
        v: [".o_notification_manager .o_notification.border-danger"] for v in _VERSIONS_D9
    },
    "fil_ariane": {
        v: [".o_breadcrumb", ".breadcrumb"] for v in _VERSIONS_D9
    },
    "recherche_facette": {
        v: [".o_searchview_facet", ".o_facet_values"] for v in _VERSIONS_D9
    },
    "ignorer": {
        v: [".o_form_button_cancel", "button[aria-label='Discard']",
            "button[aria-label='Annuler']"]
        for v in _VERSIONS_D9
    },
}


class CleSelecteurInconnueError(KeyError):
    """La clé demandée n'existe pas dans la table — jamais un silence qui ferait échouer un
    clic sur une liste vide sans dire pourquoi."""


def selecteurs(cle: str, version: tuple[int, int] | None, **valeurs) -> list[str]:
    """Sélecteurs candidats pour `cle`, résolus pour `version` — prêts pour
    `click_first_actionable(page, selecteurs(...), quoi=...)`.

    `version=None` (détection indisponible) retombe sur la version D9 la plus RÉCENTE connue —
    un choix explicite et documenté, jamais un mélange silencieux de plusieurs versions.
    `valeurs` complète les gabarits paramétrés (ex. `methode="action_confirm"` pour
    `bouton_action`).
    """
    if cle not in _TABLE:
        raise CleSelecteurInconnueError(
            f"clé de sélecteur inconnue : {cle!r} (connues : {sorted(_TABLE)})")
    par_version = _TABLE[cle]
    v = version if version in par_version else max(par_version)
    gabarits = par_version[v]
    return [g.format(**valeurs) if "{" in g else g for g in gabarits]


def odoo_attendre_inactif(page, timeout: int = 8000) -> None:
    """Attend que l'indicateur de chargement Odoo soit masqué — best-effort : son absence pure
    et simple (page déjà stable, ou version qui ne l'affiche pas pour cette action) n'est jamais
    une erreur."""
    try:
        page.locator(selecteurs("indicateur_chargement", None)[0]).wait_for(
            state="hidden", timeout=timeout)
    except Exception:
        pass


def odoo_url_action(context, *, action: int | str | None = None, menu_id: int | str | None = None,
                    model: str | None = None, view_type: str | None = None,
                    record_id: int | str | None = None) -> str:
    """URL vers une action Odoo — forme dépendant de la version détectée (`context.odoo_version`,
    posée par `environment.odoo_session`) :

    - `>= (17, 2)` (web client récent) : `/odoo/action-<action>` (+ `/<record_id>` si fourni) —
      la seule forme du client récent qui ne dépend pas de connaître le slug lisible d'un modèle
      (non disponible ici).
    - sinon (D9 : 16.0, 17.0 — web client historique) : `/web#action=<action>&menu_id=<menu_id>
      &model=<model>&view_type=<view_type>` (+ `&id=<record_id>` si fourni), même motif que
      `environment.navigate_menu`.

    Au moins `action` est requis dans les deux formes ; `menu_id`/`model`/`view_type`/`record_id`
    sont ajoutés à la forme historique s'ils sont fournis, jamais inventés.
    """
    base = context.odoo_url.rstrip("/")
    version = getattr(context, "odoo_version", None)
    recent = version is not None and version >= (17, 2)
    if recent:
        if action is None:
            raise ValueError("odoo_url_action : 'action' est requis pour la forme /odoo/… (>= 17.2)")
        url = f"{base}/odoo/action-{action}"
        if record_id is not None:
            url += f"/{record_id}"
        return url
    parties = []
    if action is not None:
        parties.append(f"action={action}")
    if menu_id is not None:
        parties.append(f"menu_id={menu_id}")
    if model is not None:
        parties.append(f"model={model}")
    if view_type is not None:
        parties.append(f"view_type={view_type}")
    if record_id is not None:
        parties.append(f"id={record_id}")
    return f"{base}/web#" + "&".join(parties)


# Identifiant Odoo dans l'URL après une action (création/sauvegarde) — deux conventions selon la
# version, même motif que `connectors/odoo.py::_ID_DEPUIS_URL_ODOO` (dupliqué ici : ce fichier vit
# hors du paquet `testpilot`, dans la bibliothèque de steps à plat — même raison que les sidecars
# dupliqués entre `environment.py` et `execution/behave_result.py`).
_ID_DEPUIS_URL = re.compile(r"[?&#]id=(\d+)\b|/(\d+)(?:[/?#]|$)")


def id_depuis_url(url: str) -> int | None:
    """L'id Odoo porté par `url` (légale ou récente), `None` si absent — jamais deviné."""
    m = _ID_DEPUIS_URL.search(url)
    if not m:
        return None
    brut = m.group(1) or m.group(2)
    return int(brut) if brut else None
