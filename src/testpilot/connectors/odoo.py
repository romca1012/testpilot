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
from urllib.parse import urljoin, urlparse

from testpilot import config
from testpilot.connectors.base import Connector
# Perception UI pure (formulaire, sonde HTTP) : PARTAGÉE avec les autres connecteurs
# (`connectors/_web_helpers.py`, audit multi-connecteurs 2026-09-08) — rien ici n'a jamais été
# spécifique à Odoo. Réexportées pour ne pas casser un import existant
# (`from testpilot.connectors.odoo import build_probe_url, extract_form`).
from testpilot.connectors._web_helpers import (  # noqa: F401
    build_probe_url,
    extract_form,
    http_probe,
    lire_message_erreur_visible,
)

logger = logging.getLogger(__name__)

# Racines et périmètre du crawl (étape 1.1 du plan de consolidation) — DUPLIQUÉS depuis
# `scripts/crawl_domaine.py` (`RACINES`/`_HORS_PERIMETRE`), pas importés : ce script est
# AUTONOME (utilisable en CLI sans le moindre projet ni connecteur, `python
# scripts/crawl_domaine.py`) et doit donc rester capable de tourner sans dépendre d'ici. Deux
# points d'entrée, une seule vérité voulue : `tests/test_crawl_polymorphisme.py` tient l'accord
# des deux copies, comme `FIELD_FALLBACK_FILE_ENV` le fait déjà pour un autre couple de constantes
# dupliquées entre le paquet et la bibliothèque de steps.
_CRAWL_RACINES = ["/my/home", "/myservices"]
_CRAWL_HORS_PERIMETRE = re.compile(
    r"^/(web|odoo)(/|$|#)|^/@/|^/website/add/|/web/static|/web/session/logout"
    r"|nav_tabs_content|/export(/|$)|\.(css|js|png|jpg|jpeg|svg|ico|woff2?)$",
    re.IGNORECASE)


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

    @classmethod
    def from_project(cls, project: dict | None, **overrides) -> "OdooConnector":
        """Connecteur branché sur la connexion du PROJET (décision 0005).

        L'exploration doit observer l'application du projet, pas une instance globale.
        Chaque valeur vide retombe sur la config (projet sans connexion saisie).
        """
        project = project or {}
        return cls.from_config(
            url=project.get("base_url") or config.ODOO_URL,
            database=project.get("database") or config.ODOO_DB,
            user=project.get("username") or config.ODOO_USER,
            password=project.get("password") or config.ODOO_PASSWORD,
            **overrides,
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

    def attempt_login(self, username: str, password: str) -> dict:
        try:
            return self._run_in_browser(self._attempt_login_sync, username, password)
        except Exception as exc:  # perception best-effort : jamais fatal pour l'agent
            logger.warning("[odoo] attempt_login a échoué : %s", exc)
            return {"submitted": False, "url": "", "message": "", "error": str(exc)[:200]}

    def _attempt_login_sync(self, username: str, password: str) -> dict:
        """Un contexte de navigateur FRAIS et JETABLE — jamais `self._page` : la session
        persistante (`_ensure_page`) est déjà authentifiée avec les VRAIS identifiants du
        projet, et y retenter une connexion avec des identifiants de SCÉNARIO ne reproduirait
        pas l'état « pas encore connecté » que le scénario veut observer."""
        self._ensure_page()  # s'assure que self._browser existe (démarrage paresseux)
        contexte = self._browser.new_context()
        try:
            page = contexte.new_page()
            page.set_default_timeout(self._timeout_ms)
            page.goto(f"{self._url}/web/login?db={self._database}")
            page.wait_for_selector("input[name='login']", state="attached",
                                   timeout=self._timeout_ms)
            page.locator("input[name='login']").fill(username, force=True)
            page.locator("input[name='password']").fill(password, force=True)
            page.locator("input[name='password']").press("Enter")
            page.wait_for_load_state("networkidle")
            return {"submitted": True, "url": page.url,
                   "message": lire_message_erreur_visible(page), "error": ""}
        finally:
            contexte.close()

    # ── Crawl de l'annuaire (étape 1.1 du plan de consolidation) ────────────────
    def crawl_roots(self, page) -> list[str]:
        """Racines HISTORIQUES du portail (décision `0020`) — indépendantes de `page`, à
        l'inverse du défaut générique : comportement STRICTEMENT inchangé."""
        return list(_CRAWL_RACINES)

    def crawl_exclusion_pattern(self) -> re.Pattern:
        """Périmètre HISTORIQUE : le portail client, jamais le back-office Odoo (`/web`, `/odoo`)
        — voir `scripts/crawl_domaine.py` pour la décision assumée en détail."""
        return _CRAWL_HORS_PERIMETRE

    def crawl_follow_hash_anchors(self) -> bool:
        """Comportement HISTORIQUE inchangé : un `href="#..."` reste TOUJOURS un onglet interne,
        jamais une transition de page, sur le portail Odoo."""
        return False

    def crawl_relogin_hook(self):
        """Connexion portail Odoo (`/web/login?db=…`) SUR LA PAGE DU CRAWL — délègue à
        `behave_runtime.steps_library._base_helpers.playwright_login`, la même fonction que
        `scripts/crawl_domaine.py` utilise depuis toujours, plutôt que d'en réimplémenter une
        variante qui dériverait de la vraie (celle-ci porte la post-condition qui compte :
        attendre d'avoir RÉELLEMENT quitté `/web/login`, pas une simple absence de requête réseau).

        ⚠️ **Import différé, et seulement utilisable après le montage de `sys.path` que fait
        l'appelant** (`exploration_service.py::_crawl`, seul appelant réel de cette méthode pour un
        crawl) : `_base_helpers` vit dans `behave_runtime/steps_library/`, hors du paquet
        `testpilot` — l'importer au niveau du module romprait le démarrage normal du serveur, qui
        ne monte jamais ce chemin. `_ensure_page()` ci-dessus, lui, gère sa PROPRE session
        (perception `inspect_form`/`discover_route`) et n'a jamais eu ce besoin.
        """
        def _login(ctx) -> None:
            import _base_helpers as H
            ctx.odoo_url = self._url
            ctx.odoo_db = self._database
            ctx.odoo_user = self._user
            ctx.odoo_password = self._password
            H.playwright_login(ctx)
        return _login

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
        """Sonde HTTP HEAD→GET. Méthode (pas fonction directe) pour rester surchargeable
        hors-ligne en test (``conn._http_probe = lambda url: {...}``) — la logique réelle est
        partagée (``_web_helpers.http_probe``)."""
        return http_probe(url)
