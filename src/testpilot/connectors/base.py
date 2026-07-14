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

from abc import ABC, abstractmethod


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
