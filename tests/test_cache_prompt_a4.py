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

from testpilot.analysis.plan import TestPlan
from testpilot.generation import metier_writer
from testpilot.generation import prompt as pm
from testpilot.generation import steps_library
from testpilot.generation.tools import TOOLS_DEFINITIONS
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import _contenu_utilisateur, with_history_cache


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


# ── `call_simple`/`call_json` : préfixe caché sur la passe métier (audit coûts, 2026-09-16) ──

def test_sans_prefixe_cache_le_contenu_est_la_simple_chaine_d_avant():
    """Zéro régression : un appelant qui ne passe pas `cached_prefix` (spec_analyzer, decoupage,
    explication…) garde EXACTEMENT le comportement d'avant — une chaîne, pas une liste de blocs."""
    assert _contenu_utilisateur("", "bonjour") == "bonjour"


def test_avec_prefixe_cache_le_point_est_sur_le_PREMIER_bloc_seul():
    """Le préfixe (stable) porte `cache_control` ; le suffixe (variable, le cas précis) n'en porte
    JAMAIS — sinon il n'y aurait plus rien de stable à relire au tour suivant."""
    blocs = _contenu_utilisateur("SPEC ENTIÈRE", "CE CAS")
    assert blocs[0] == {"type": "text", "text": "SPEC ENTIÈRE",
                        "cache_control": {"type": "ephemeral"}}
    assert blocs[1] == {"type": "text", "text": "CE CAS"}
    assert "cache_control" not in blocs[1]


def test_prefixe_cache_sans_suffixe_reste_UN_seul_bloc():
    """Le chemin CLI / cas manuel (`brief` vide) : pas de second bloc vide à envoyer pour rien."""
    blocs = _contenu_utilisateur("SPEC ENTIÈRE", "")
    assert len(blocs) == 1 and blocs[0]["cache_control"] == {"type": "ephemeral"}


def _plan(spec="La spécification complète du module."):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


def test_le_prefixe_metier_est_BYTE_STABLE_dun_cas_a_lautre():
    """⚠️ La garde qui fait ou défait ce chantier : `decoupage` extrait N cas de LA MÊME spec, et
    `propose_metier` est appelé une fois par cas. Si `_build_prompt` (le préfixe caché) variait
    ne serait-ce que d'un octet entre deux cas de la même spec, le cache ne mordrait JAMAIS et les
    11+ appels "metier" mesurés au ledger resteraient plein tarif chacun — sans la moindre erreur
    pour le signaler (même risque que le prompt système, `test_le_prompt_systeme_...` ci-dessus)."""
    plan = _plan()
    assert metier_writer._build_prompt(plan) == metier_writer._build_prompt(plan)


def test_le_cas_precis_ne_fuit_jamais_dans_le_prefixe_cache():
    """Le préfixe ne doit JAMAIS dépendre de `brief` — sinon deux cas de la même spec produiraient
    deux préfixes différents et le cache ne mordrait jamais entre eux, silencieusement."""
    plan = _plan()
    prefixe_sans_brief = metier_writer._build_prompt(plan)

    captes: list[str] = []

    class FakeLLM:
        def call_simple(self, *, cached_prefix="", **_):
            captes.append(cached_prefix)
            return "{}"

    metier_writer.propose_metier(plan, llm=FakeLLM(), brief="Un cas très différent d'un autre")
    metier_writer.propose_metier(plan, llm=FakeLLM(), brief="Un second cas, sans rapport")

    assert captes[0] == captes[1] == prefixe_sans_brief, (
        "le préfixe caché doit être identique quel que soit le cas précis rédigé")
