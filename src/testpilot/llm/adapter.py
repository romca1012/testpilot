"""Adaptateur LLM Anthropic — appels simples (analyse/rapport) et outillés (génération).

Incrément 0 : fournisseur unique Anthropic. Le prompt système est mis en cache
(``cache_control: ephemeral``) et un second point de cache est posé sur le dernier bloc
d'historique — le préfixe d'outils accumulé par la boucle ReAct est relu à coût réduit
au tour suivant (coût ~linéaire au lieu de quadratique).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from testpilot import config

logger = logging.getLogger(__name__)


@dataclass
class ToolUseBlock:
    """Appel d'outil normalisé (indépendant du SDK)."""
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """Réponse LLM normalisée + usage tokens (pour le suivi de coût)."""
    stop_reason: str  # "end_turn" | "tool_use"
    text_blocks: list[str] = field(default_factory=list)
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def text(self) -> str:
        return "\n".join(self.text_blocks)


def with_history_cache(messages: list[dict]) -> list[dict]:
    """Pose un point de cache ``ephemeral`` sur le dernier bloc de l'historique.

    Pur : ne mute jamais l'entrée (copie superficielle). No-op si rien de cachable.
    """
    if not messages:
        return messages
    out = list(messages)
    last = dict(out[-1])
    content = last.get("content")
    if isinstance(content, str):
        if not content:
            return messages
        last["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(content, list) and content:
        new_content = list(content)
        for i in range(len(new_content) - 1, -1, -1):
            if isinstance(new_content[i], dict):
                new_content[i] = {**new_content[i], "cache_control": {"type": "ephemeral"}}
                break
        else:
            return messages
        last["content"] = new_content
    else:
        return messages
    out[-1] = last
    return out


class LLMAdapter:
    """Interface unifiée pour les appels Anthropic avec ou sans outils."""

    def __init__(self):
        self._client = None

    def _client_(self):
        if self._client is None:
            import anthropic

            key = config.ANTHROPIC_API_KEY
            if not key:
                raise EnvironmentError(
                    "ANTHROPIC_API_KEY manquante — renseignez-la dans .env."
                )
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    @staticmethod
    def _track(cost_tracker, resp, model_id: str, label: str) -> None:
        if cost_tracker is None:
            return
        usage = getattr(resp, "usage", None)
        cost_tracker.track_call(
            model=model_id,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
            label=label,
        )

    def call_simple(self, *, system_prompt: str = "", user_content: str = "",
                    model: str = "", max_tokens: int = 2000, cost_tracker=None,
                    label: str = "call_simple") -> str:
        """Appel sans outil (analyse de spec, recommandations). Retourne le texte brut."""
        model_id = model or config.MODEL_FAST
        resp = self._client_().messages.create(
            model=model_id,
            max_tokens=max_tokens,
            temperature=0.1,
            system=[{"type": "text", "text": system_prompt or "Réponds de façon concise."}],
            messages=[{"role": "user", "content": user_content}],
        )
        self._track(cost_tracker, resp, model_id, label)
        return resp.content[0].text if resp.content else ""

    def call_with_tools(self, *, system_prompt: str, messages: list[dict], tools: list[dict],
                        model: str = "", max_tokens: int = 8000, cost_tracker=None,
                        label: str = "generation") -> tuple[LLMResponse, object]:
        """Appel outillé (boucle ReAct). Retourne (réponse normalisée, réponse SDK brute)."""
        model_id = model or config.MODEL_GENERATION
        resp = self._client_().messages.create(
            model=model_id,
            max_tokens=max_tokens,
            temperature=0.2,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=with_history_cache(messages),
        )
        self._track(cost_tracker, resp, model_id, label)
        return self._parse(resp), resp

    @staticmethod
    def _parse(resp) -> LLMResponse:
        texts, calls = [], []
        for block in resp.content:
            if getattr(block, "type", "") == "text" and getattr(block, "text", ""):
                texts.append(block.text)
            elif getattr(block, "type", "") == "tool_use":
                calls.append(ToolUseBlock(id=block.id, name=block.name, input=block.input))
        usage = resp.usage
        return LLMResponse(
            stop_reason="tool_use" if calls else "end_turn",
            text_blocks=texts,
            tool_calls=calls,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
        )
