"""Connecteur Odoo — implémentation concrète de ``Connector`` (§6).

Deux modes de perception cohabitent dans un seul connecteur, comme l'exige l'interface :

- MOITIÉ RPC (odoorpc) — reprise du connecteur historique : ``get_schema``, ``search``,
  ``read``, ``create``, ``delete``. L'agent et les steps n'importent jamais odoorpc.
- MOITIÉ PERCEPTION UI (Playwright) — ``inspect_form`` observe le VRAI formulaire portail
  rendu, y compris les champs cachés injectés côté serveur (cause racine
  ``missing_server_context`` du §5). ``discover_route`` sonde une route en HTTP léger.

Le navigateur Playwright est démarré paresseusement : un usage purement RPC ne le lance
jamais. Les fonctions de parsing DOM et de construction d'URL sont pures (testables
hors-ligne), la couche réseau est isolée dans des méthodes surchargeables.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from testpilot import config
from testpilot.connectors.base import Connector

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


class OdooConnector(Connector):

    def __init__(self, url: str, database: str, user: str, password: str, *,
                 headless: bool = True, timeout_ms: int = 15_000) -> None:
        self._url = url.rstrip("/")
        self._database = database
        self._user = user
        self._password = password
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._client = None       # odoorpc.ODOO — initialisé par connect()
        self._playwright = None
        self._browser = None
        self._page = None         # démarré paresseusement à la 1re inspection UI
        self._executor = None     # thread dédié Playwright (voir _run_in_browser)

    @classmethod
    def from_config(cls, **overrides) -> "OdooConnector":
        return cls(
            url=overrides.get("url", config.ODOO_URL),
            database=overrides.get("database", config.ODOO_DB),
            user=overrides.get("user", config.ODOO_USER),
            password=overrides.get("password", config.ODOO_PASSWORD),
            headless=overrides.get("headless", True),
        )

    # ── Cycle de vie ──────────────────────────────────────────────────────────
    def connect(self) -> None:
        import odoorpc
        parsed = urlparse(self._url)
        protocol = "jsonrpc+ssl" if parsed.scheme == "https" else "jsonrpc"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._client = odoorpc.ODOO(host, protocol=protocol, port=port)
        self._client.login(self._database, self._user, self._password)

    def disconnect(self) -> None:
        # Le navigateur est thread-affine : sa fermeture passe par le thread worker.
        if self._executor is not None:
            def _close():
                if self._browser is not None:
                    self._browser.close()
                if self._playwright is not None:
                    self._playwright.stop()
            try:
                self._executor.submit(_close).result(timeout=30)
            except Exception as exc:
                logger.warning("[odoo] fermeture navigateur : %s", exc)
            self._executor.shutdown(wait=False)
            self._executor = None
        self._page = None
        self._browser = None
        self._playwright = None
        self._client = None

    # ── Perception RPC ─────────────────────────────────────────────────────────
    def get_schema(self, model: str) -> dict:
        return self._client.env[model].fields_get()

    def search(self, model: str, filters: list, limit: int = 0) -> list[int]:
        kwargs = {"limit": limit} if limit else {}
        return self._client.env[model].search(filters, **kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self._client.env[model].browse(ids).read(fields)

    # ── Perception UI (Playwright) ─────────────────────────────────────────────
    def inspect_form(self, page_url: str) -> dict:
        """Observe le vrai formulaire portail rendu (champs réels, champs cachés injectés)."""
        try:
            return self._run_in_browser(self._inspect_sync, page_url)
        except Exception as exc:  # perception best-effort : jamais fatal pour l'agent
            logger.warning("[odoo] inspect_form a échoué sur %s : %s", page_url, exc)
            return {"fields": [], "submission": {}, "error": str(exc)[:200]}

    def _inspect_sync(self, page_url: str) -> dict:
        """Séquence Playwright réelle — exécutée DANS le thread worker (voir _run_in_browser)."""
        page = self._ensure_page()
        target = page_url if page_url.startswith("http") else urljoin(self._url + "/", page_url.lstrip("/"))
        page.goto(target)
        page.wait_for_load_state("networkidle")
        result = extract_form(page)
        result["error"] = ""
        return result

    def discover_route(self, path_pattern: str, sample_id: int | None = None) -> dict:
        """Sonde une route en HTTP léger (HEAD puis repli GET) : statut + méthode."""
        url = build_probe_url(self._url, path_pattern, sample_id)
        return self._http_probe(url)

    # ── Écriture (runtime / teardown) ──────────────────────────────────────────
    def create(self, model: str, vals: dict) -> int:
        return self._client.env[model].create(vals)

    def delete(self, model: str, ids: list[int]) -> bool:
        self._client.env[model].browse(ids).unlink()
        return True

    # ── Interne (réseau isolé, surchargeable en test) ──────────────────────────
    def _run_in_browser(self, fn, *args):
        """Exécute une opération Playwright dans un thread dédié SANS boucle asyncio.

        La génération tourne dans une boucle asyncio ; or l'API SYNC de Playwright refuse de
        s'exécuter dans une boucle active (« Sync API inside the asyncio loop »). On isole donc
        toutes les interactions navigateur dans un unique thread worker — qui n'a aucune boucle
        d'événements — et où vivent les objets Playwright (thread-affinité)."""
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="odoo-playwright")
        return self._executor.submit(fn, *args).result()

    def _ensure_page(self):
        """Démarre Playwright + session portail authentifiée (DANS le thread worker)."""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        page = self._browser.new_context().new_page()
        page.set_default_timeout(self._timeout_ms)
        # Connexion web Odoo (portail). force=True : les inputs de login Odoo ne sont pas
        # toujours « visibles » au sens Playwright (widgets/overlay) → fill classique timeout.
        page.goto(f"{self._url}/web/login?db={self._database}")
        page.wait_for_selector("input[name='login']", state="attached", timeout=self._timeout_ms)
        page.locator("input[name='login']").fill(self._user, force=True)
        page.locator("input[name='password']").fill(self._password, force=True)
        page.locator("input[name='password']").press("Enter")
        page.wait_for_load_state("networkidle")
        self._page = page
        return page

    def _http_probe(self, url: str) -> dict:
        """Sonde HTTP HEAD→GET. Isolée pour être surchargée hors-ligne en test."""
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
