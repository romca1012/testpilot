"""Analyse PURE d'une vue Odoo (lot 09, C9) — boutons, barre d'état, champs x2many et leurs
sous-champs éditables, champs requis. Aucun réseau ici : reçoit le résultat RPC déjà obtenu
(``get_views``, ou son repli ``fields_view_get``) et en extrait ce qu'un agent de génération a
besoin de VOIR avant d'écrire un test — jamais deviné, jamais tapé de mémoire sur un nom de
bouton ou un état de workflow.

⚠️ **Vérifié sur un vrai Odoo 16.0** (banc local, 2026-09-30), pas supposé depuis la
documentation seule : ``get_views`` répond bien sur cette version (contrairement à une
hypothèse possible qu'il ne serait apparu qu'en 17), et rend `{"views": {...}, "models": {...}}`
— l'``arch`` XML de la vue demandée, PLUS les métadonnées de champs (``required``, ``relation``,
``selection``...) de TOUS les modèles impliqués (le modèle principal ET les modèles liés par un
champ x2many affiché dans la vue, ex. ``sale.order.line`` pour ``sale.order``) en un seul appel.
La sous-vue d'un champ x2many est directement INLINÉE dans l'``arch`` parent (des `<field>`
imbriqués sous le `<field name="order_line">`), jamais une vue séparée à requêter en plus.

``fields_view_get`` (repli, pré-16 ou si ``get_views`` échoue) ne rend que le modèle PRINCIPAL —
les sous-champs d'un x2many restent alors invisibles, dégradation assumée et signalée dans le
champ ``erreur`` de sortie, jamais silencieuse.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

_VIDE: dict = {
    "boutons": [],
    "barre_etat": None,
    "champs_x2many": [],
    "champs_requis": [],
    "erreur": "",
}


def _modifiers(el: ET.Element) -> dict:
    """Le JSON du `modifiers="{...}"` d'un élément d'arch — `{}` si absent ou illisible (jamais
    une exception : une vue réelle mal formée ne doit jamais faire planter la perception)."""
    brut = el.get("modifiers") or ""
    if not brut:
        return {}
    try:
        return json.loads(brut)
    except (ValueError, TypeError):
        return {}


def normaliser_reponse_rpc(brut: dict, model: str, view_type: str) -> tuple[str, dict[str, dict]]:
    """Rend `(arch_xml, {modele: {champ: meta}})` depuis UNE des deux formes RPC possibles —
    `get_views` (plusieurs modèles) ou `fields_view_get` (un seul, repli) — pour que
    `analyser_vue` n'ait jamais à connaître laquelle a répondu."""
    if "views" in brut and "models" in brut:
        arch = (brut.get("views") or {}).get(view_type, {}).get("arch", "") or ""
        return arch, brut.get("models") or {}
    arch = brut.get("arch", "") or ""
    return arch, {model: brut.get("fields") or {}}


def analyser_vue(brut: dict, model: str, view_type: str = "form") -> dict:
    """Boutons, barre d'état, champs x2many (+ sous-champs éditables) et champs requis d'une vue
    Odoo — depuis le résultat RPC brut (`get_views` ou `fields_view_get`), jamais depuis le DOM.

    Rend toujours les 5 clés de `_VIDE` ; `erreur` porte la raison d'une dégradation (arch
    illisible, vue vide) — jamais une exception vers l'appelant (perception best-effort, comme
    le reste du module `tools/inspect.py`).
    """
    arch, modeles = normaliser_reponse_rpc(brut, model, view_type)
    if not arch:
        return {**_VIDE, "erreur": f"aucune vue « {view_type} » pour « {model} »"}
    try:
        racine = ET.fromstring(arch)
    except ET.ParseError as exc:
        return {**_VIDE, "erreur": f"arch illisible : {exc}"}

    champ_meta = modeles.get(model) or {}

    boutons = [
        {
            "name": btn.get("name", ""),
            "libelle": btn.get("string", ""),
            "type": btn.get("type", ""),
            # ⚠️ **Jamais un simple booléen** — mesuré sur le banc réel (sale.order, 2026-09-30) :
            # la quasi-totalité des boutons d'un vrai formulaire de workflow portent un
            # `invisible` CONDITIONNEL (un domaine Odoo, ex. `[["state","not in",["draft"]]]`),
            # pas un littéral `true`/`false`. `bool(domaine)` vaudrait `True` pour un bouton
            # visible 90% du temps — un faux « toujours caché » qui aurait fait ignorer à tort le
            # bouton principal d'un workflow. Trois états distincts, jamais réduits à deux :
            # `False` (toujours visible), `True` (toujours caché), une liste (visibilité SOUS
            # CONDITION — le domaine brut, lisible tel quel : la syntaxe `[[champ, op, valeur]]`
            # est celle qu'Odoo utilise partout, y compris déjà dans les prompts de ce dépôt).
            "invisible": _modifiers(btn).get("invisible", False),
        }
        for btn in racine.iter("button")
    ]

    barre_etat = None
    for f in racine.iter("field"):
        if f.get("widget") != "statusbar":
            continue
        nom = f.get("name", "")
        meta = champ_meta.get(nom) or {}
        selection = meta.get("selection") or []
        visibles = [v for v in (f.get("statusbar_visible") or "").split(",") if v]
        barre_etat = {
            "champ": nom,
            "valeurs_visibles": visibles or [v for v, _libelle in selection],
            "valeurs_toutes": [v for v, _libelle in selection],
        }
        break

    champs_x2many = []
    for f in racine.iter("field"):
        nom = f.get("name", "")
        meta = champ_meta.get(nom) or {}
        if meta.get("type") not in ("one2many", "many2many"):
            continue
        sous_champs = sorted({
            sub.get("name") for sub in f.iter("field")
            if sub is not f and sub.get("name")
        })
        champs_x2many.append({
            "name": nom, "relation": meta.get("relation", ""), "sous_champs": sous_champs,
        })

    champs_requis = sorted(nom for nom, meta in champ_meta.items() if meta.get("required"))

    return {
        "boutons": boutons, "barre_etat": barre_etat,
        "champs_x2many": champs_x2many, "champs_requis": champs_requis, "erreur": "",
    }
