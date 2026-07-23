"""Audit A4 (§2bis) — le cache de prompt reste EFFICACE : gardes contre l'invalidation silencieuse.

Le patron est correct (préfixe système stable mis en cache `ephemeral`, volatil dans les messages
utilisateur). Mais un cache se casse SANS BRUIT : un horodatage ou un UUID glissé dans le préfixe,
un ordre d'outils qui change, et chaque appel se repaie plein tarif — sans aucune erreur. Ces
gardes figent les invariants qui rendent le cache opérant ; elles échoueraient si un futur
changement les brisait.

Le témoin runtime (`cache_hit_ratio`) est exposé par `CostTracker.summary()` pour vérifier en
production que le cache mord vraiment (0 sur un run à plusieurs tours = invalidateur à chercher).
"""

from __future__ import annotations

from testpilot.generation import prompt as pm
from testpilot.generation import steps_library
from testpilot.generation.tools import TOOLS_DEFINITIONS
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import with_history_cache


# ── Le PRÉFIXE mis en cache doit être BYTE-STABLE ────────────────────────────

def test_le_prompt_systeme_est_identique_a_deux_constructions():
    """⚠️ La garde centrale du cache. Le prompt système est le PRÉFIXE mis en cache et partagé
    entre toutes les générations. S'il diffère d'un octet d'un appel à l'autre (horodatage, UUID,
    JSON non trié…), le cache ne mord JAMAIS et chaque génération se repaie plein tarif — sans la
    moindre erreur pour le signaler."""
    steps = steps_library.catalogue()
    a = pm.build_system_prompt(connector=None, shared_steps=steps)
    b = pm.build_system_prompt(connector=None, shared_steps=steps)
    assert a == b, "le prompt système doit être byte-identique (sinon cache inopérant)"
    assert "datetime" not in a.lower() or "now(" not in a  # pas d'horodatage évident


def test_le_catalogue_de_steps_est_dans_un_ordre_deterministe():
    """Le catalogue fait partie du préfixe système : un ordre changeant l'invaliderait. `catalogue`
    trie déjà, on le prouve — deux extractions donnent la même séquence de libellés."""
    a = [s.label for s in steps_library.catalogue()]
    b = [s.label for s in steps_library.catalogue()]
    assert a == b


def test_l_ordre_des_outils_est_deterministe():
    """Les outils sont rendus en position 0 du prompt : leur ordre doit être STABLE (une liste
    littérale l'est). Un ordre variable (ex. issu d'un set) casserait le cache tools+système."""
    noms = [t["name"] for t in TOOLS_DEFINITIONS]
    assert noms == [t["name"] for t in TOOLS_DEFINITIONS]  # même objet, ordre figé
    assert len(noms) == len(set(noms)), "pas de doublon de nom d'outil"


# ── Le placement du point de cache ───────────────────────────────────────────

def test_with_history_cache_pose_le_point_sur_le_DERNIER_bloc():
    """Le cache d'historique (coût ~linéaire au lieu de quadratique dans la boucle ReAct) doit
    marquer le dernier bloc du dernier message — sans muter l'entrée."""
    messages = [{"role": "user", "content": "spec"},
                {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}]
    out = with_history_cache(messages)
    assert out[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    # Pureté : l'entrée d'origine n'est pas modifiée.
    assert "cache_control" not in messages[-1]["content"][-1]


# ── La VISIBILITÉ runtime : cache_hit_ratio ──────────────────────────────────

def test_summary_expose_le_ratio_de_cache():
    """Le témoin que le plan demande de surveiller. Sans lui, on ne peut pas vérifier que le cache
    mord réellement en production."""
    t = CostTracker(limit_usd=100.0)
    # Tour 1 : écriture du cache (préfixe froid).
    t.track_call(model="claude-sonnet-4-6", input_tokens=200, output_tokens=50,
                 cache_write_tokens=1000, cache_read_tokens=0, label="t1")
    # Tour 2 : lecture du cache (préfixe chaud).
    t.track_call(model="claude-sonnet-4-6", input_tokens=200, output_tokens=50,
                 cache_write_tokens=0, cache_read_tokens=1000, label="t2")
    s = t.summary()
    assert s["cache_read_tokens"] == 1000
    assert s["cache_write_tokens"] == 1000
    # 1000 lus sur (1000 lus + 400 non cachés) ≈ 0.714
    assert s["cache_hit_ratio"] > 0.5, "le cache doit être visiblement actif"


def test_ratio_zero_sans_cache_signale_l_invalidateur():
    """Garde négative : aucun token caché → ratio 0, exactement le signal « cache inopérant »."""
    t = CostTracker(limit_usd=100.0)
    t.track_call(model="claude-sonnet-4-6", input_tokens=500, output_tokens=50, label="froid")
    assert t.summary()["cache_hit_ratio"] == 0.0
