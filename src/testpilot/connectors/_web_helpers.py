"""Perception UI PURE, partagée entre TOUS les connecteurs web (Odoo, générique, …).

Extrait de ``connectors/odoo.py`` (audit multi-connecteurs, 2026-09-08) : ces fonctions
n'ont jamais rien eu de spécifique à Odoo — elles lisent une page RENDUE (formulaire, lien,
réponse HTTP), jamais l'API RPC. Les dupliquer dans chaque nouveau connecteur aurait fait
deux endroits où corriger un bug d'extraction de formulaire (ex. un type de champ mal
reconnu) sans que le second ne le sache jamais.

``odoo.py`` réexporte ``build_probe_url``/``extract_form`` pour ne pas casser les imports
existants (``from testpilot.connectors.odoo import build_probe_url, extract_form``).
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Champs de formulaire à ignorer : jetons techniques, pas des champs métier.
_IGNORED_FIELD_PREFIXES = ("_",)
_IGNORED_FIELD_NAMES = {"csrf_token"}


def build_probe_url(base_url: str, path_pattern: str, sample_id: int | None = None) -> str:
    """Construit l'URL absolue à sonder. Pur (aucun réseau).

    ``{id}`` dans le motif est substitué par ``sample_id`` s'il est fourni.
    """
    pattern = path_pattern or "/"
    if "{id}" in pattern and sample_id is not None:
        pattern = pattern.replace("{id}", str(sample_id))
    elif "{id}" in pattern:
        pattern = pattern.replace("{id}", "")
    return urljoin(base_url.rstrip("/") + "/", pattern.lstrip("/"))


def extract_form(page) -> dict:
    """Extrait champs + mécanisme de soumission d'une page rendue. Pur vis-à-vis du réseau.

    ``page`` est un objet duck-typé (Playwright Page ou fake de test) exposant
    ``query_selector_all`` / ``query_selector``. Retour :
    ``{fields:[{name,required,type}], submission:{mechanism,endpoint,trigger_selector}}``.
    """
    fields: list[dict] = []
    seen: set[str] = set()
    for el in page.query_selector_all("input, select, textarea"):
        name = el.get_attribute("name") or el.get_attribute("id") or ""
        if not name or name in seen:
            continue
        if name in _IGNORED_FIELD_NAMES or name.startswith(_IGNORED_FIELD_PREFIXES):
            continue
        seen.add(name)
        tag = (el.get_attribute("__tag__") or "").lower()  # fake de test
        input_type = el.get_attribute("type") or tag or "text"
        fields.append({
            "name": name,
            "required": el.get_attribute("required") is not None,
            "type": input_type,
        })

    submission = _detect_submission(page)
    return {"fields": fields, "submission": submission}


def _detect_submission(page) -> dict:
    """Déduit le mécanisme de soumission : endpoint du <form> + sélecteur déclencheur."""
    form = page.query_selector("form")
    endpoint = form.get_attribute("action") if form else ""
    trigger = page.query_selector("button[type='submit'], input[type='submit'], button.btn-primary")
    trigger_selector = ""
    if trigger is not None:
        name = trigger.get_attribute("name")
        trigger_selector = f"[name='{name}']" if name else "button[type='submit']"
    return {
        "mechanism": "button_click",
        "endpoint": endpoint or "",
        "trigger_selector": trigger_selector,
    }


def tenter_connexion_generique(page, user: str, password: str) -> bool:
    """Détection de connexion GÉNÉRIQUE (pas de convention d'URL à connaître, à la différence
    d'Odoo) — partagée entre ``GenericWebConnector`` (exécution) et le crawl générique
    (exploration, audit multi-connecteurs 2026-09-08) : les deux affrontent le même problème,
    « repérer un formulaire de connexion sur une page qu'on n'a jamais vue ».

    Heuristique : un mot de passe est l'identifiant le plus fiable d'un formulaire de connexion —
    on cherche ``input[type=password]``, on prend le premier champ texte/email de la PAGE comme
    identifiant (scope volontairement simple, pas un `closest('form')` — un premier jet à affiner
    si un formulaire réel la met en défaut), on remplit et on valide.

    Identifiant/mot de passe VIDES, ou aucun champ mot de passe sur la page : on considère
    l'application accessible sans connexion et on continue tel quel — mieux vaut explorer sans
    authentification que de bloquer sur une hypothèse de connexion fausse.

    Retourne ``True`` si une tentative a réellement été soumise (jamais si la page ou les
    identifiants ne s'y prêtaient pas).
    """
    if not user or not password:
        return False
    champ_mdp = page.query_selector("input[type='password']")
    if champ_mdp is None:
        return False
    champ_identifiant = page.query_selector("input[type='email'], input[type='text']")
    if champ_identifiant is None:
        logger.warning("[connexion-générique] mot de passe détecté sans champ identifiant"
                        " — connexion non tentée")
        return False
    champ_identifiant.fill(user, force=True)
    champ_mdp.fill(password, force=True)
    champ_mdp.press("Enter")
    page.wait_for_load_state("networkidle")
    return True


def http_probe(url: str) -> dict:
    """Sonde HTTP HEAD→GET. Isolée pour être surchargée hors-ligne en test."""
    last = ""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"url": url, "status": resp.status, "method": method, "note": "accessible"}
        except urllib.error.HTTPError as exc:
            return {"url": url, "status": exc.code, "method": method,
                    "note": exc.reason or "réponse HTTP d'erreur"}
        except (urllib.error.URLError, OSError) as exc:
            last = str(getattr(exc, "reason", exc))
            continue
    return {"url": url, "status": 0, "method": "GET", "note": f"injoignable : {last}"}
