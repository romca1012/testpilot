"""Adaptateur LLM Anthropic — appels simples (analyse/rapport) et outillés (génération).

Incrément 0 : fournisseur unique Anthropic. Le prompt système est mis en cache
(``cache_control: ephemeral``) et un second point de cache est posé sur le dernier bloc
d'historique — le préfixe d'outils accumulé par la boucle ReAct est relu à coût réduit
au tour suivant (coût ~linéaire au lieu de quadratique).
"""

from __future__ import annotations

import json
import logging
import re
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
    stop_reason: str  # "end_turn" | "tool_use" — signal de FLUX (y a-t-il un tool à exécuter ?)
    # ⚠️ Le stop_reason BRUT de l'API (`end_turn` | `tool_use` | `max_tokens` | `refusal` | …),
    # distinct du signal de flux ci-dessus qui l'écrasait. `max_tokens` = réponse TRONQUÉE : un
    # Gherkin coupé ne doit pas passer pour un test valide (§2bis A3). `refusal` = décliné par
    # sécurité. Sans ce champ, les deux étaient masqués en `end_turn` et pris pour un succès.
    raw_stop_reason: str = ""
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


def _contenu_utilisateur(cached_prefix: str, user_content: str):
    """Le `content` d'un message utilisateur pour `call_simple`/`call_json`.

    ⚠️ **Pourquoi ce découpage (audit coûts, 2026-09-16).** `metier_writer.propose_metier` est
    appelé UNE FOIS PAR CAS pour la MÊME spécification (`decoupage` en a extrait N) — jusqu'ici, le
    texte complet de la spec repartait en clair, en entier, à chaque appel : 11 appels "metier" du
    ledger réel, aucun cache, plein tarif à chaque fois. Sans `cached_prefix`, un seul bloc texte
    (comportement d'avant, zéro régression pour tout appelant qui ne le passe pas). Avec, DEUX
    blocs — le préfixe STABLE (la spec, les règles) marqué `cache_control: ephemeral`, suivi du
    texte VARIABLE (le brief du cas précis, jamais caché puisqu'il change à chaque appel). Le
    premier appel d'un lot paie l'écriture du cache (~1,25x) ; les suivants, dans les ~5 minutes,
    relisent ce préfixe à ~0,1x — à condition qu'il dépasse le seuil minimal de mise en cache du
    modèle (silencieux sinon, jamais une erreur : `usage.cache_read_input_tokens` le confirme).
    """
    if not cached_prefix:
        return user_content
    blocs = [{"type": "text", "text": cached_prefix, "cache_control": {"type": "ephemeral"}}]
    if user_content:
        blocs.append({"type": "text", "text": user_content})
    return blocs


# Modèles qui REJETTENT `temperature` (400) et veulent la pensée adaptative + `effort`
# (doc API Claude : Sonnet 5, Opus 4.8/4.7, Fable 5). Les autres (Haiku 4.5, Sonnet 4.6) gardent
# `temperature`. On teste par PRÉFIXE : les alias n'ont pas de suffixe de date, mais on veut aussi
# couvrir un éventuel id daté.
_MODELES_ADAPTATIFS = ("claude-sonnet-5", "claude-opus-4-8", "claude-opus-4-7", "claude-fable-5",
                       "claude-mythos-5")


def _params_echantillonnage(model: str, *, temperature: float, effort: str = "high") -> dict:
    """Les BONS paramètres d'échantillonnage selon le modèle (migration Sonnet 5, gated).

    ⚠️ **Pourquoi model-aware et pas un simple `temperature=`.** Sonnet 5 et Opus 4.8/4.7 rejettent
    `temperature` par un **400** ; ils veulent `thinking:{type:"adaptive"}` + `output_config:{effort}`.
    Haiku 4.5 et Sonnet 4.6 (notre défaut ACTUEL) l'acceptent. Ce helper rend l'un ou l'autre — donc
    **zéro régression sur le défaut** (Sonnet 4.6 reste dans la branche `temperature`), et le code est
    prêt le jour où le porteur bascule la génération sur Sonnet 5.

    ⚠️ **`extra_body`, jamais `temperature=` en direct (2026-09-11).** Le SDK `anthropic` 1.x a
    RETIRÉ `temperature`/`top_p`/`top_k` de la signature de `messages.create()` — pour TOUS les
    modèles, pas seulement ceux qui la refusent côté API. `pyproject.toml` pinnait `anthropic>=0.40`
    sans plafond : une image reconstruite a tiré la 1.2.0 et cassé CETTE branche (Haiku 4.5,
    Sonnet 4.6 y compris) avec un `TypeError: Messages.create() got an unexpected keyword argument
    'temperature'` — pas un 400, un vrai crash Python, avant même que la requête ne parte. La
    passer dans `extra_body` la remet telle quelle dans le JSON envoyé à l'API : même valeur sur le
    fil, compatible avec la signature 1.x.
    """
    m = (model or "").lower()
    if any(m.startswith(p) for p in _MODELES_ADAPTATIFS):
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}
    return {"extra_body": {"temperature": temperature}}


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
                    cached_prefix: str = "", model: str = "", max_tokens: int = 2000,
                    cost_tracker=None, label: str = "call_simple") -> str:
        """Appel sans outil (analyse de spec, recommandations). Retourne le texte brut.

        `cached_prefix` — bloc STABLE placé AVANT `user_content`, avec un point de cache
        (`cache_control: ephemeral`). Pour un même appelant qui répète le même préfixe sur
        plusieurs appels rapprochés (ex. la spec complète, une fois par cas) — voir
        `_contenu_utilisateur`. Vide (défaut) : comportement d'avant, un seul bloc texte.
        """
        model_id = model or config.MODEL_FAST
        resp = self._client_().messages.create(
            model=model_id,
            max_tokens=max_tokens,
            **_params_echantillonnage(model_id, temperature=0.1),
            system=[{"type": "text", "text": system_prompt or "Réponds de façon concise."}],
            messages=[{"role": "user", "content": _contenu_utilisateur(cached_prefix, user_content)}],
        )
        self._track(cost_tracker, resp, model_id, label)
        # Réponse tronquée : la sortie (souvent du JSON à parser) peut être incomplète. On le
        # SIGNALE plutôt que de rendre en silence un texte coupé qui échouera au parsing avec une
        # cause obscure. (Le durcissement dur vit dans la boucle ReAct — §2bis A3.)
        if getattr(resp, "stop_reason", "") == "max_tokens":
            logger.warning("call_simple[%s] : réponse TRONQUÉE (max_tokens=%s) — "
                           "sortie possiblement incomplète", label, max_tokens)
        return resp.content[0].text if resp.content else ""

    def call_json(self, *, system_prompt: str = "", user_content: str = "",
                  cached_prefix: str = "", schema: dict,
                  model: str = "", max_tokens: int = 2000, cost_tracker=None,
                  label: str = "call_json") -> dict:
        """Rend un DICT — via SORTIES STRUCTURÉES quand le modèle les honore (§2bis A2).

        `output_config.format` fait GARANTIR par l'API un JSON conforme au `schema` : une classe
        entière d'échecs de parsing (JSON tronqué, texte autour, virgule en trop) disparaît.

        ⚠️ **Repli TRANSPARENT, zéro régression.** Les sorties structurées sont bornées à certains
        modèles (Haiku 4.5, Sonnet 5, Opus 4.8 ; PAS garanti sur Sonnet 4.6). Si l'API refuse
        `output_config` (400 / paramètre inconnu), on retombe EXACTEMENT sur le comportement
        d'avant : `call_simple` + extraction tolérante `{…}`. Le repli n'est pris que sur un échec
        de REQUÊTE (aucun double coût) ; une requête honorée n'est facturée qu'une fois.
        """
        model_id = model or config.MODEL_FAST
        try:
            resp = self._client_().messages.create(
                model=model_id,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system_prompt or "Réponds en JSON."}],
                messages=[{"role": "user",
                          "content": _contenu_utilisateur(cached_prefix, user_content)}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as exc:  # output_config refusé (modèle/version) → repli, sans surcoût
            logger.warning("call_json[%s] : sortie structurée indisponible (%s) — repli parsing "
                           "tolérant", label, type(exc).__name__)
            return self._json_par_repli(system_prompt, cached_prefix, user_content, model_id,
                                        max_tokens, cost_tracker, label)
        self._track(cost_tracker, resp, model_id, label)
        if getattr(resp, "stop_reason", "") == "max_tokens":
            logger.warning("call_json[%s] : réponse TRONQUÉE (max_tokens=%s) — JSON possiblement "
                           "incomplet", label, max_tokens)
        text = next((b.text for b in resp.content
                     if getattr(b, "type", "") == "text"), "") if resp.content else ""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # output_config honoré mais JSON illisible (ne devrait pas arriver) : extraction de
            # secours, SANS re-appeler (pas de double coût).
            m = re.search(r"\{.*\}", text or "", re.DOTALL)
            return json.loads(m.group(0)) if m else {}

    def _json_par_repli(self, system_prompt, cached_prefix, user_content, model_id, max_tokens,
                        cost_tracker, label) -> dict:
        """Le comportement d'AVANT : appel simple + extraction tolérante du premier objet JSON."""
        raw = self.call_simple(system_prompt=system_prompt, cached_prefix=cached_prefix,
                               user_content=user_content, model=model_id, max_tokens=max_tokens,
                               cost_tracker=cost_tracker, label=label)
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}

    def call_with_tools(self, *, system_prompt: str, messages: list[dict], tools: list[dict],
                        model: str = "", max_tokens: int = 8000, cost_tracker=None,
                        label: str = "generation") -> tuple[LLMResponse, object]:
        """Appel outillé (boucle ReAct). Retourne (réponse normalisée, réponse SDK brute)."""
        model_id = model or config.MODEL_GENERATION
        resp = self._client_().messages.create(
            model=model_id,
            max_tokens=max_tokens,
            **_params_echantillonnage(model_id, temperature=0.2),
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
            raw_stop_reason=getattr(resp, "stop_reason", "") or "",
            text_blocks=texts,
            tool_calls=calls,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
        )
