"""Interface commune à tous les connecteurs.

Un connecteur encapsule la communication avec le système testé (Odoo, REST, …).
L'agent et les steps Behave n'interagissent qu'avec cette interface — jamais avec
odoorpc, requests ou une librairie concrète. Implémenter un connecteur = hériter de
``Connector`` et définir les méthodes abstraites.

Les méthodes de perception (``get_schema``, ``search``/``read``, ``inspect_form``,
``discover_route``) matérialisent l'exploration « boîte noire » de l'application vivante
(§6) : l'agent observe le système en marche, il ne lit jamais son code source.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse

# Exclusion GÉNÉRIQUE par défaut (étape 1.1 du plan de consolidation, 2026-09-15 — audit « Le
# pari Mabl/Testim ») : sans convention d'URL à connaître, seul ce qui est UNIVERSEL à toute
# application web peut être exclu sans deviner son périmètre. Même motif que
# `scripts/crawl_domaine.py::_HORS_PERIMETRE_GENERIQUE` (audit multi-connecteurs 2026-09-08) —
# repris ici comme le défaut de l'INTERFACE, plutôt que dupliqué dans chaque connecteur générique.
_HORS_PERIMETRE_GENERIQUE = re.compile(
    r"\.(css|js|png|jpg|jpeg|svg|ico|woff2?|pdf)$", re.IGNORECASE)


class Connector(ABC):

    # ── Cycle de vie ──────────────────────────────────────────────────────────
    @abstractmethod
    def connect(self) -> None:
        """Ouvre la connexion et authentifie la session."""

    @abstractmethod
    def disconnect(self) -> None:
        """Ferme proprement la connexion."""

    # ── Perception (lecture / exploration) ───────────────────────────────────
    @abstractmethod
    def get_schema(self, model: str) -> dict:
        """Définition des champs du modèle : {field: {type, string, required, relation, …}}."""

    @abstractmethod
    def search(self, model: str, filters: list, limit: int = 0) -> list[int]:
        """Recherche et retourne des IDs (jamais de records ni de dicts)."""

    @abstractmethod
    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        """Lit les champs demandés pour une liste d'IDs."""

    @abstractmethod
    def inspect_form(self, page_url: str) -> dict:
        """Observe un formulaire réel : {fields: [{name, required, type}], submission: {...}, error: ""}."""

    @abstractmethod
    def discover_route(self, path_pattern: str, sample_id: int | None = None) -> dict:
        """Sonde une route : {url, status, method, note}."""

    @abstractmethod
    def attempt_login(self, username: str, password: str) -> dict:
        """Tente une connexion avec CES identifiants précis (valides, erronés, verrouillés...)
        et rend ce qui s'affiche RÉELLEMENT : {submitted, url, message, error}.

        Perception, pas un état durable — sur un contexte de navigateur JETABLE, jamais la
        session persistante de l'exploration : appelable plusieurs fois de suite avec des
        identifiants différents (2026-09-16, amendement §4.3-bis étendu — un cas générait
        « Sorry, this user has been locked out. » quand l'application affiche en réalité
        « Epic sadface: Sorry, this user has been locked out. » : l'agent avait deviné ce texte
        au lieu de l'observer). `message` est le texte du premier message d'erreur visible après
        soumission (`""` si aucun) ; `error` porte la raison d'un échec de PERCEPTION (SSO/2FA,
        aucun formulaire détecté) — jamais confondu avec un `message` d'erreur applicatif."""

    @abstractmethod
    def attempt_form_submission(self, page_url: str, field_values: dict,
                                model: str = "") -> dict:
        """Remplit CES champs (par nom technique) sur le VRAI formulaire, le soumet, observe ce
        qui s'affiche VRAIMENT, et NETTOIE ce qui a été créé si le connecteur en a les moyens —
        {submitted, url, message, cleaned_up, error}.

        Réservée aux projets qui ont explicitement autorisé la calibration en écriture
        (`project.calibration_writes_enabled`, migration 45, 2026-09-16) : vérifié par
        l'appelant (le tool `attempt_form_submission`), pas ici — un connecteur ne connaît pas
        les réglages du projet. `model`, quand fourni, identifie ce qui a été créé pour le
        supprimer (RPC) ; sans capacité de suppression garantie, un connecteur DOIT refuser
        (`NotImplementedError`) plutôt que de laisser une donnée de calibration sans filet."""

    # ── Écriture (runtime des tests / teardown) ──────────────────────────────
    @abstractmethod
    def create(self, model: str, vals: dict) -> int:
        """Crée un enregistrement et retourne son ID."""

    @abstractmethod
    def delete(self, model: str, ids: list[int]) -> bool:
        """Supprime les enregistrements dont les IDs sont fournis."""

    # ── Optionnel ─────────────────────────────────────────────────────────────
    def rules(self) -> str:
        """Règles spécifiques au connecteur, injectées dans le prompt. Vide par défaut."""
        return ""

    # ── Crawl de l'annuaire (étape 1.1 du plan de consolidation, 2026-09-15) ────
    #
    # ⚠️ **Ce que ces 4 méthodes remplacent.** `exploration_service.py::_crawl` choisissait ses
    # paramètres de crawl par un `if connector_type == "odoo": ... else: ...` en dur — ajouter un
    # 3ᵉ type de connecteur exigeait de modifier CE service, pas seulement d'écrire une nouvelle
    # classe. Exactement le défaut que `connectors/factory.py::build_connector` a déjà fermé une
    # fois pour la génération et la réparation (2026-09-11) ; le crawl était le dernier point
    # encore couplé. Les défauts CONCRETS ci-dessous sont le comportement GÉNÉRIQUE déjà mesuré et
    # éprouvé (SauceDemo) — c'est lui qui devient « le défaut », pas un cas spécial de plus.

    def crawl_roots(self, page) -> list[str]:
        """Chemin(s) où DÉMARRER le parcours BFS du crawl.

        Défaut générique : là où la connexion a RÉELLEMENT laissé la page — jamais une racine en
        dur. Sur une application dont `/` EST le formulaire de connexion (ex. SauceDemo), y
        retourner après coup perdrait la session tout juste établie (bug réel, 2026-09-11) :
        `page` est déjà la page du navigateur juste après le premier appel du repli de
        `crawl_relogin_hook()`.
        """
        return [urlparse(page.url).path or "/"]

    def crawl_exclusion_pattern(self) -> re.Pattern:
        """Motif des chemins à NE JAMAIS visiter pendant le crawl.

        Défaut générique : uniquement les assets statiques, universels à toute application web —
        sans convention d'URL à connaître, exclure davantage reviendrait à deviner le périmètre
        d'une application qu'on ne connaît pas.
        """
        return _HORS_PERIMETRE_GENERIQUE

    def crawl_follow_hash_anchors(self) -> bool:
        """Un lien `href="#..."` doit-il être tenté comme une transition de PAGE (clic + lecture
        de l'URL réelle), au-delà du simple changement d'état d'onglet ?

        Défaut générique : oui — beaucoup d'applications modernes (SPA) n'ont pas d'autre
        convention de navigation qu'un clic qui change l'URL via l'History API (cas réel mesuré
        sur le catalogue SauceDemo, 2026-09-11).
        """
        return True

    @abstractmethod
    def crawl_relogin_hook(self):
        """Rend une fonction `(ctx) -> None` qui (re)connecte `ctx.page` — appelée une première
        fois AVANT le crawl, puis à nouveau à chaque fois que le navigateur redémarre après un
        crash pendant le parcours.

        Pas de défaut générique possible : la connexion elle-même (identifiants, formulaire,
        convention d'URL, absence éventuelle de connexion) est ce qui distingue le plus un
        connecteur d'un autre — contrairement aux trois méthodes ci-dessus, purement structurelles.
        """

    def discover_menus(self, page) -> list[dict]:
        """Modèles métier accessibles au compte connecté via un mécanisme de MENU propre à
        l'application — {menu, model} — au-delà de ce que le crawl atteint par les liens.

        Complément du crawl, jamais un remplacement (décision 2026-09-18, module Parc IT/Odoo) :
        `crawl_exclusion_pattern` exclut délibérément le back-office d'un connecteur comme Odoo
        (`/web`, `/odoo`), donc un module purement back-office reste hors du crawl QUOI QU'IL
        ARRIVE — son nom de modèle technique doit venir d'ailleurs, ou `inspect_schema` ne peut
        même pas être appelé dessus (il faut déjà connaître le nom pour l'interroger).

        `page` est la session déjà AUTHENTIFIÉE du crawl (`crawl_relogin_hook` vient de tourner) :
        aucune nouvelle connexion, aucun accès RPC ne doit être nécessaire ici.

        Défaut générique : rien — sans convention de menu propre à l'application (une page web
        quelconque n'en a pas), il n'y a rien à énumérer sans deviner."""
        return []
