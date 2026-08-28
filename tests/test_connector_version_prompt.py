"""La VERSION déclarée du connecteur (migration 38) — simple contexte informatif transmis au
prompt, jamais une règle de comportement. Périmètre volontairement resserré : `Connector.rules()`
ne change pas de signature, aucune règle par version n'existe encore. Seul le FAIT de la version,
quand elle est connue, doit atteindre l'agent — silence complet quand elle est indéterminée.
"""

from __future__ import annotations

from testpilot.generation import prompt as prompt_mod
from testpilot.generation import repair_agent
from testpilot.generation.interfaces import Connector


class _ConnecteurBidon(Connector):
    """Un connecteur minimal, SANS règles propres — sert à isoler l'effet de `connector_version`
    de celui de `Connector.rules()` (déjà testé ailleurs, jamais retouché ici). Les méthodes
    abstraites sont des coquilles vides : seul le nom de la classe (via `_nom_connecteur`) et
    l'absence de règles nous intéressent ici."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def get_schema(self, model: str) -> dict: return {}
    def search(self, model: str, filters: list, limit: int = 0) -> list[int]: return []
    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]: return []
    def inspect_form(self, page_url: str) -> dict: return {}
    def discover_route(self, path_pattern: str, sample_id: int | None = None) -> dict: return {}
    def create(self, model: str, vals: dict) -> int: return 0
    def delete(self, model: str, ids: list[int]) -> bool: return True


def test_la_version_absente_ne_produit_aucune_mention():
    """'' (indéterminée) : le prompt système reste BYTE-IDENTIQUE à avant ce lot (cache de
    prompt, A4 — cf. `test_cache_prompt_a4.py`) — aucun bloc ajouté pour ne rien dire."""
    sans_rien = prompt_mod.build_system_prompt(connector=None, shared_steps=[])
    avec_version_vide = prompt_mod.build_system_prompt(
        connector=None, shared_steps=[], connector_version="")
    assert "Version déclarée" not in avec_version_vide
    assert sans_rien == avec_version_vide


def test_la_version_declaree_apparait_dans_le_prompt_systeme():
    prompt = prompt_mod.build_system_prompt(
        connector=_ConnecteurBidon(), shared_steps=[], connector_version="17")
    assert "Version déclarée : 17" in prompt
    # Dans le bloc ajouté EN FIN de prompt, pas ailleurs — même placement que les règles.
    assert prompt.rstrip().endswith("</regles_connecteur>")
    assert "Version déclarée : 17" in prompt[prompt.rindex('<regles_connecteur'):]


def test_la_version_declaree_apparait_dans_le_prompt_de_reparation():
    prompt = repair_agent.build_repair_prompt(
        connector=_ConnecteurBidon(), connector_type=None, connector_version="17")
    assert "Version déclarée : 17" in prompt


def test_la_version_absente_laisse_le_prompt_de_reparation_inchange():
    prompt = repair_agent.build_repair_prompt(connector=None, connector_type=None)
    assert "Version déclarée" not in prompt
