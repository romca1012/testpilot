"""Principe 1 — la signature de stall se dérive du RUNTIME, jamais du texte de l'agent.

`failure_signature` indexait sur `scenario_name`, écrit par l'agent dans le `.feature`. Comme
l'agent réécrit le fichier ENTIER à chaque tentative, **renommer un scénario suffisait à changer
la signature** — donc à masquer l'absence de progrès. Le garde-fou dépendait du composant qu'il
encadre : le motif de la journée (docs/PRINCIPES.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from testpilot import config
from testpilot.guardrails.repair_circuit import CircuitState, evaluate, failure_signature
from testpilot.verdict import defect_taxonomy as dt


@dataclass
class F:
    scenario_name: str = "[Nominal]"
    step_text: str = ""
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = "TypeError: 'int' object is not subscriptable"


def test_renommer_un_scenario_ne_change_PAS_la_signature():
    """LE test du principe 1 ici — il échoue sur le code d'avant.

    L'agent réécrit le `.feature` à chaque tentative : s'il renomme, le stall devient aveugle et
    le budget brûle sur un test qui n'avance pas.
    """
    avant = failure_signature([F(scenario_name="[Nominal] Demande complète")])
    apres = failure_signature([F(scenario_name="[NOMINAL] Demande de matériel — cas passant")])
    assert avant == apres


def test_le_libelle_du_step_ne_change_pas_la_signature():
    """`step_text` est aussi de l'agent (0015)."""
    a = failure_signature([F(step_text='Alors le champ "team_id" pointe vers "Matériel"')])
    b = failure_signature([F(step_text="Alors le ticket est créé")])
    assert a == b


def test_le_message_ecrit_par_l_agent_ne_change_pas_la_signature():
    """Le texte APRÈS `ASSERT FAILED:` est rédigé par l'agent — seul le TYPE compte."""
    a = failure_signature([F(failure_type="assertion", raw="ASSERT FAILED: le total vaut 3")])
    b = failure_signature([F(failure_type="assertion", raw="ASSERT FAILED: autre chose encore")])
    assert a == b


# ── Ce que la signature DOIT distinguer : les faits du runtime ────────────────

def test_deux_types_d_exception_differents_donnent_deux_signatures():
    a = failure_signature([F(raw="TypeError: 'int' object is not subscriptable")])
    b = failure_signature([F(raw="AttributeError: 'NoneType' object has no attribute 'id'")])
    assert a != b, "changer d'erreur EST un progrès : la signature doit le voir"


def test_le_nombre_d_echecs_compte():
    un = failure_signature([F()])
    deux = failure_signature([F(scenario_name="A"), F(scenario_name="B")])
    assert un != deux, "passer de 2 échecs à 1 est un progrès réel"


def test_une_cause_differente_donne_une_signature_differente():
    typeerror = failure_signature([F(raw="TypeError: pas indexable")])
    timeout = failure_signature([F(failure_type="ui_timeout",
                                   raw="playwright._impl._errors.TimeoutError: Timeout 30000ms")])
    assert typeerror != timeout


def test_aucun_echec_donne_une_signature_vide():
    assert failure_signature([]) == ""


def test_un_echec_sans_type_identifiable_reste_signable():
    """Pas de type → la signature ne doit pas devenir vide (vide = « aucun échec »)."""
    s = failure_signature([F(failure_type="unknown", raw="quelque chose a mal tourné")])
    assert s and s != ""
    assert "sans-type" in s


def test_la_signature_ne_lit_qu_un_texte_du_runtime():
    """Garde structurelle : `runtime_error_text` n'inclut jamais `step_text` (0015)."""
    f = F(step_text="ALORS_CE_LIBELLE_NE_DOIT_PAS_APPARAITRE", raw="TypeError: x")
    assert "ALORS_CE_LIBELLE" not in dt.runtime_error_text(f)
    assert "ALORS_CE_LIBELLE" not in failure_signature([f])


# ── Le stall, et le fait gênant qu'il ne se déclenche jamais par défaut ───────

def test_le_stall_est_INATTEIGNABLE_avec_le_budget_par_defaut():
    """Constat documenté, pas un bug : `stall_limit`=3 > budget par défaut=2.

    `evaluate` coupe sur le plafond d'itérations avant que `repeat_count` atteigne 3. Ce test
    fige le fait pour qu'il ne se perde pas — s'il casse, c'est que la configuration a changé et
    que le commentaire de `CircuitState` doit être mis à jour.
    """
    assert config.REPAIR_STALL_LIMIT > config.REPAIR_BUDGET_DEFAULT, (
        "le stall est devenu atteignable par défaut — mettre à jour la docstring de CircuitState")

    circuit = CircuitState(max_iterations=config.REPAIR_BUDGET_DEFAULT,
                           stall_limit=config.REPAIR_STALL_LIMIT)
    echecs = [F()]
    for _ in range(config.REPAIR_BUDGET_DEFAULT):
        circuit.record(failure_signature(echecs))
    assert not circuit.stalled                      # jamais atteint…
    assert evaluate(circuit, echecs).outcome == "max_iterations"   # …le plafond coupe avant


def test_le_stall_fonctionne_quand_le_budget_le_permet():
    """Avec un budget large, le garde reprend son rôle — et il est désormais CORRECT."""
    circuit = CircuitState(max_iterations=10, stall_limit=3)
    echecs = [F()]
    for _ in range(3):
        circuit.record(failure_signature(echecs))
    assert circuit.stalled
    assert evaluate(circuit, echecs).outcome == "stalled"


def test_le_stall_n_est_plus_aveugle_a_un_renommage():
    """Le scénario du défaut : 3 tentatives identiques, renommées à chaque fois."""
    circuit = CircuitState(max_iterations=10, stall_limit=3)
    for nom in ("[Nominal] v1", "[Nominal] v2 reformulé", "[NOMINAL] encore autrement"):
        circuit.record(failure_signature([F(scenario_name=nom)]))
    assert circuit.stalled, "renommer ne doit plus masquer l'absence de progrès"
