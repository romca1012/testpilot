"""Connecteur web GÉNÉRIQUE — implémentation de ``Connector`` (§6) pour une application SANS
API de modèle exploitable (audit multi-connecteurs, 2026-09-08).

Contexte : ``OdooConnector`` doit sa moitié RPC (``get_schema``/``search``/``read``/``create``/
``delete``) à une particularité d'Odoo — n'importe quel modèle, même d'un module métier maison,
s'y interroge génériquement. La plupart des applications web n'offrent RIEN d'équivalent : ce
connecteur assume l'absence de cette moitié et se limite à la perception UI (Playwright), déjà
partagée avec Odoo (``_web_helpers.py``) — ``inspect_form``/``discover_route`` suffisent à
l'exploration, et la bibliothèque de steps ``generic/`` (déjà scindée de celle d'Odoo, audit DA
2026-08-13) suffit à l'exécution : aucune des deux n'a jamais eu besoin de connaître le nom de
l'application ciblée.

Détection de connexion GÉNÉRIQUE (pas de convention d'URL à connaître) : un mot de passe est
identifiant fiable d'un formulaire de connexion — on cherche `input[type=password]`, on prend le
premier champ texte/email du MÊME formulaire comme identifiant, on remplit et on valide. Aucune
identification (identifiant/mot de passe vides, ou aucun mot de passe trouvé sur la page) → on
considère l'application accessible sans connexion et on continue tel quel.
"""

from __future__ import annotations

import concurrent.futures
import logging
from urllib.parse import urljoin

from testpilot.connectors._web_helpers import (
    build_probe_url,
    extract_form,
    http_probe,
    tenter_connexion_et_lire_resultat,
    tenter_connexion_generique,
)
from testpilot.connectors._sonde_saisie import sonder_formulaire
from testpilot.connectors.base import Connector

logger = logging.getLogger(__name__)

_MESSAGE_SANS_MODELE = (
    "Ce connecteur n'a pas de modèle de données interrogeable (application sans API générique, "
    "à la différence d'Odoo) — l'exploration et l'exécution reposent uniquement sur les "
    "formulaires observés dans le navigateur (inspect_form/discover_route + steps génériques)."
)


class GenericWebConnector(Connector):
    """Connecteur pour une application web quelconque, identifiée par sa seule URL."""

    def __init__(self, url: str, user: str = "", password: str = "", *,
                 headless: bool = True, timeout_ms: int = 15_000) -> None:
        self._url = url.rstrip("/")
        self._user = user
        self._password = password
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._page = None       # démarré paresseusement à la 1re inspection UI
        self._executor = None   # thread dédié Playwright (voir _run_in_browser)
        self._tentative_connexion_faite = False

    @classmethod
    def from_project(cls, project: dict | None, **overrides) -> GenericWebConnector:
        """Connecteur branché sur la connexion du PROJET (décision 0005) — mêmes colonnes
        génériques que les autres connecteurs (``base_url``/``username``/``password``)."""
        project = project or {}
        return cls(
            url=overrides.get("url", project.get("base_url") or ""),
            user=overrides.get("user", project.get("username") or ""),
            password=overrides.get("password", project.get("password") or ""),
            **{k: v for k, v in overrides.items() if k not in ("url", "user", "password")},
        )

    # ── Cycle de vie ──────────────────────────────────────────────────────────
    def connect(self) -> None:
        """Rien à ouvrir à l'avance (pas de session RPC) — la page se lance paresseusement à
        la première perception, comme pour la moitié UI d'Odoo."""

    def disconnect(self) -> None:
        if self._executor is not None:
            def _close():
                if self._browser is not None:
                    self._browser.close()
                if self._playwright is not None:
                    self._playwright.stop()
            try:
                self._executor.submit(_close).result(timeout=30)
            except Exception as exc:
                logger.warning("[web-générique] fermeture navigateur : %s", exc)
            self._executor.shutdown(wait=False)
            self._executor = None
        self._page = None
        self._browser = None
        self._playwright = None

    # ── Perception RPC : AUCUNE (voir docstring du module) ──────────────────────
    def get_schema(self, model: str) -> dict:
        raise NotImplementedError(_MESSAGE_SANS_MODELE)

    def search(self, model: str, filters: list, limit: int = 0) -> list[int]:
        raise NotImplementedError(_MESSAGE_SANS_MODELE)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        raise NotImplementedError(_MESSAGE_SANS_MODELE)

    def create(self, model: str, vals: dict) -> int:
        raise NotImplementedError(_MESSAGE_SANS_MODELE)

    def delete(self, model: str, ids: list[int]) -> bool:
        raise NotImplementedError(_MESSAGE_SANS_MODELE)

    # ── Perception UI (Playwright) — partagée avec Odoo ─────────────────────────
    def inspect_form(self, page_url: str) -> dict:
        try:
            return self._run_in_browser(self._inspect_sync, page_url)
        except Exception as exc:  # perception best-effort : jamais fatal pour l'agent
            logger.warning("[web-générique] inspect_form a échoué sur %s : %s", page_url, exc)
            return {"fields": [], "submission": {}, "error": str(exc)[:200]}

    def _inspect_sync(self, page_url: str) -> dict:
        page = self._ensure_page()
        target = page_url if page_url.startswith("http") else urljoin(self._url + "/", page_url.lstrip("/"))
        page.goto(target)
        page.wait_for_load_state("networkidle")
        result = extract_form(page)
        result["sonde"] = sonder_formulaire(page, page.url or target)  # lot 12 : ne lève jamais
        result["error"] = ""
        return result

    def discover_route(self, path_pattern: str, sample_id: int | None = None) -> dict:
        url = build_probe_url(self._url, path_pattern, sample_id)
        return self._http_probe(url)

    def attempt_form_submission(self, page_url: str, field_values: dict,
                                model: str = "") -> dict:
        raise NotImplementedError(
            "ce connecteur ne peut pas garantir la suppression de ce qu'il crée (aucune API de "
            "modèle, cf. docstring du module) — la calibration en écriture par soumission de "
            "formulaire est réservée à un connecteur qui expose create/delete (Odoo).")

    def attempt_login(self, username: str, password: str) -> dict:
        try:
            return self._run_in_browser(self._attempt_login_sync, username, password)
        except Exception as exc:  # perception best-effort : jamais fatal pour l'agent
            logger.warning("[web-générique] attempt_login a échoué : %s", exc)
            return {"submitted": False, "url": "", "message": "", "error": str(exc)[:200]}

    def _attempt_login_sync(self, username: str, password: str) -> dict:
        """Un contexte de navigateur FRAIS et JETABLE — jamais `self._page` : la session
        persistante est peut-être déjà authentifiée avec les VRAIS identifiants du projet
        (`_ensure_page`), et y retenter une connexion avec des identifiants de SCÉNARIO (compte
        verrouillé, mot de passe erroné...) ne reproduirait pas l'état « pas encore connecté »
        que le scénario veut observer."""
        self._ensure_page()  # s'assure que self._browser existe (démarrage paresseux)
        contexte = self._browser.new_context()
        try:
            page = contexte.new_page()
            page.set_default_timeout(self._timeout_ms)
            page.goto(self._url)
            page.wait_for_load_state("networkidle")
            return tenter_connexion_et_lire_resultat(page, username, password)
        finally:
            contexte.close()

    # ── Crawl de l'annuaire (étape 1.1 du plan de consolidation) ────────────────
    # `crawl_roots`/`crawl_exclusion_pattern`/`crawl_follow_hash_anchors` : le défaut GÉNÉRIQUE de
    # `Connector` convient tel quel (c'est lui qui a été mesuré sur SauceDemo) — seule la connexion
    # est propre à ce connecteur.
    def crawl_relogin_hook(self):
        """(Re)connexion GÉNÉRIQUE : mêmes identifiants et même détection que `_ensure_page`, sur
        la page du CRAWL plutôt que sur la page interne de perception (`self._page`) — les deux
        affrontent le même problème (aucune convention d'URL à connaître) et réutilisent donc la
        même fonction PARTAGÉE (`_web_helpers.tenter_connexion_generique`).

        ⚠️ **Mesure la page de CONNEXION elle-même, AVANT de s'authentifier** (correctif du
        2026-09-15 — audit « Le pari Mabl/Testim », faux positif trouvé en diagnostiquant un cas
        réel). Le BFS du crawl démarre APRÈS la connexion, là où elle a laissé la page
        (`Connector.crawl_roots`) — sans cette mesure, les champs de connexion (`user-name`,
        `password`…) ne sont JAMAIS visités, jamais mesurés, et « Points de vigilance » (`
        smoke_check.check_champs_existants`) signale à tort ces champs comme inconnus sur
        CHAQUE cas qui s'y réfère, quelle que soit la fraîcheur du crawl.

        Résultat déposé sur `ctx.page_connexion` (`(route, infos)`), lu par
        `exploration_service._crawl` après le crawl pour compléter `pages` — jamais l'écraser
        (une mesure du BFS, plus complète, prime toujours). Best-effort : un échec de mesure ne
        doit jamais empêcher la connexion elle-même.
        """
        def _connexion(ctx) -> None:
            ctx.page.goto(self._url)
            ctx.page.wait_for_load_state("networkidle")
            try:
                import crawl_domaine as cd
                from testpilot.generation import domain_model
                ctx.page_connexion = (
                    domain_model.normaliser_route(ctx.page.url), cd._inspecter_page(ctx.page))
            except Exception:
                logger.warning("[web-générique] mesure de la page de connexion impossible — "
                               "ses champs resteront invisibles pour « Points de vigilance »",
                               exc_info=True)
            tenter_connexion_generique(ctx.page, self._user, self._password)
        return _connexion

    # ── Interne (réseau isolé, surchargeable en test) ──────────────────────────
    def _run_in_browser(self, fn, *args):
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="web-generique-playwright")
        return self._executor.submit(fn, *args).result()

    def _ensure_page(self):
        """Démarre Playwright et tente une connexion GÉNÉRIQUE si un formulaire de connexion
        est détecté (DANS le thread worker) — voir docstring du module."""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        page = self._browser.new_context().new_page()
        page.set_default_timeout(self._timeout_ms)
        page.goto(self._url)
        page.wait_for_load_state("networkidle")
        self._tenter_connexion_generique(page)
        self._page = page
        return page

    def _tenter_connexion_generique(self, page) -> None:
        """Délègue à la détection PARTAGÉE (``_web_helpers.tenter_connexion_generique``) — le
        crawl générique d'exploration affronte le même problème et réutilise la même fonction."""
        self._tentative_connexion_faite = tenter_connexion_generique(page, self._user, self._password)

    def _http_probe(self, url: str) -> dict:
        """Méthode (pas fonction directe) pour rester surchargeable hors-ligne en test."""
        return http_probe(url)
