"""Lot 02 (D1, D2) — la CAUSE d'une assertion dépend du TYPE du step, jamais de son libellé.

Trois familles de tests :

1. **Mesure Behave réelle** (étape 0 du lot) : `step_type` est bien dans le JSON, `Et`/`Mais` héritent
   du type du step précédent, un hook en échec ne laisse ni step ni message dans le JSON.
2. **Taxonomie** : `AssertionError` en given / when / then / hook → 4 causes, et le MÊME texte d'erreur
   avec des libellés de step différents → la même cause (non-régression de la décision 0015).
3. **Circuit de réparation** : un prérequis non rempli n'est JAMAIS envoyé en réparation automatique.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from testpilot.execution.behave_result import STEP_TYPE_HOOK, BehaveFailure, parse_behave_json
from testpilot.guardrails.repair_circuit import CircuitState, evaluate
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt


# ── 1. Behave RÉEL : ce que le JSON contient vraiment ────────────────────────────────────────

_FEATURE = textwrap.dedent("""\
    # language: fr
    Fonctionnalité: F
      Contexte:
        Soit un contexte a
        Et un contexte b
      Scénario: S
        Soit un prerequis c
        Et un prerequis d
        Quand une action e
        Mais une action f
        Alors un constat g
        Et un constat h
    """)

_STEPS = textwrap.dedent("""\
    from behave import given, when, then

    @given("un contexte a")
    def a(c): pass
    @given("un contexte b")
    def b(c): pass
    @given("un prerequis c")
    def c_(c): pass
    @given("un prerequis d")
    def d(c): pass
    @when("une action e")
    def e(c): pass
    @when("une action f")
    def f(c): pass
    @then("un constat g")
    def g(c): pass
    @then("un constat h")
    def h(c): raise AssertionError("boom")
    """)


def _lancer_behave(dossier, environment: str | None = None):
    (dossier / "features" / "steps").mkdir(parents=True)
    (dossier / "features" / "t.feature").write_text(_FEATURE, encoding="utf-8")
    (dossier / "features" / "steps" / "s.py").write_text(_STEPS, encoding="utf-8")
    if environment:
        (dossier / "features" / "environment.py").write_text(environment, encoding="utf-8")
    # Comme `BehaveRunner` : le JSON va dans un FICHIER (`-o`), le reste sur stdout/stderr.
    proc = subprocess.run([sys.executable, "-m", "behave", "--lang", "fr", "-f", "json", "-o",
                           "resultat.json", "--no-summary", "features"],
                          cwd=dossier, capture_output=True, text=True, timeout=120)
    sortie = dossier / "resultat.json"
    proc.json_output = sortie.read_text(encoding="utf-8") if sortie.exists() else ""
    return proc


def test_reel_le_json_de_behave_porte_step_type_et_et_mais_heritent(tmp_path):
    """Mesuré sur la version de behave installée : chaque step porte son type, `Et`/`Mais` héritent
    du précédent, et l'échec d'un `Et` après un `Alors` est bien un step `then`."""
    proc = _lancer_behave(tmp_path)

    resultat = parse_behave_json(proc.json_output, proc.returncode,
                                 combined_log=f"{proc.stdout}\n{proc.stderr}")

    (echec,) = resultat.failures
    assert echec.step_type == "then", "l'`Et` qui suit un `Alors` hérite de `then`"
    assert dt.classify_failure(echec) == dt.ASSERTION_MISMATCH


def test_reel_un_hook_en_echec_devient_un_echec_de_type_hook_avec_son_message(tmp_path):
    """Un `before_scenario` qui lève laisse un scénario `hook_error` SANS step en échec et SANS
    message dans le JSON : c'est le texte imprimé par Behave qui dit pourquoi."""
    proc = _lancer_behave(tmp_path, environment=textwrap.dedent("""\
        def before_scenario(context, scenario):
            raise RuntimeError("connexion refusee par l'instance")
        """))

    resultat = parse_behave_json(proc.json_output, proc.returncode,
                                 combined_log=f"{proc.stdout}\n{proc.stderr}")

    (echec,) = resultat.failures
    assert echec.step_type == STEP_TYPE_HOOK
    assert "connexion refusee par l'instance" in echec.raw
    assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE
    assert resultat.scenarios[0].status == "failed"
    assert "connexion refusee" in resultat.scenarios[0].error


def _json_avec(*steps):
    return __import__("json").dumps([{"elements": [{
        "type": "scenario", "name": "S", "status": "failed", "steps": list(steps)}]}])


def test_sans_step_type_dans_le_json_le_type_du_step_precedent_est_repris():
    """Repli si une autre version de behave n'écrivait pas `step_type` : on hérite du dernier type
    déclaré au lieu de deviner sur le libellé du step."""
    json_sortie = _json_avec(
        {"keyword": "Soit", "name": "x", "step_type": "given", "result": {"status": "passed"}},
        {"keyword": "Et", "name": "un texte quelconque",
         "result": {"status": "failed", "error_message": "ASSERT FAILED: non"}})

    resultat = parse_behave_json(json_sortie, 1)

    assert resultat.failures[0].step_type == "given"


# ── 2. Taxonomie : le type du step décide, jamais le libellé ─────────────────────────────────

def _assertion(step_type: str, libelle: str = "", message: str = "quoi que ce soit"):
    return BehaveFailure(scenario_name="s", step_text=libelle, failure_type="assertion",
                         traceback_summary="", raw=f"ASSERT FAILED: {message}",
                         step_type=step_type)


@pytest.mark.parametrize("step_type,attendue", [
    ("given", dt.PRECONDITION_NON_REMPLIE),   # D1 : le Contexte affirme un prérequis
    ("when", dt.BROKEN_TEST_CODE),            # D2 : une assertion dans une action = test cassé
    ("then", dt.ASSERTION_MISMATCH),          # le seul endroit où l'on constate l'application
    (STEP_TYPE_HOOK, dt.PRECONDITION_NON_REMPLIE),
])
def test_une_assertion_a_quatre_causes_selon_le_type_du_step(step_type, attendue):
    assert dt.classify_failure(_assertion(step_type)) == attendue


def test_non_regression_0015_le_meme_texte_avec_des_libelles_differents_donne_la_meme_cause():
    """Le libellé Gherkin est écrit par l'agent : il ne doit jamais influencer la cause."""
    libelles = ["le module est installé", "aucun enregistrement n'existe", "team_id est vide",
                "permission refusée", ""]
    for type_du_step in ("given", "when", "then"):
        causes = {dt.classify_failure(_assertion(type_du_step, libelle)) for libelle in libelles}
        assert len(causes) == 1, (type_du_step, causes)


def test_un_hook_est_un_prerequis_quel_que_soit_le_type_d_exception():
    for brut in ("TimeoutError: page.goto", "TypeError: mauvais argument",
                 "ASSERT FAILED: x", "ConnectionRefusedError: [Errno 111]"):
        echec = BehaveFailure("s", "", "hook", "", raw=brut, step_type=STEP_TYPE_HOOK)
        assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE, brut


def test_l_exception_dediee_est_reconnue_au_type_meme_sans_type_de_step():
    echec = BehaveFailure("s", "", "unknown", "",
                          raw="Traceback (most recent call last):\n  ...\n"
                              "PreconditionNonRemplieError: module absent")
    assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE


def test_les_autres_exceptions_d_un_step_when_ne_changent_pas_de_cause():
    """`TimeoutError` en `Quand` reste `wrong_field_name` (→ retest) : seule l'ASSERTION change."""
    echec = BehaveFailure("s", "", "ui_timeout", "", raw="TimeoutError: waiting for locator",
                          step_type="when")
    assert dt.classify_failure(echec) == dt.WRONG_FIELD_NAME


def test_sans_type_de_step_le_comportement_historique_est_inchange():
    assert dt.classify_failure(_assertion("")) == dt.ASSERTION_MISMATCH


def test_le_libelle_de_la_nouvelle_cause_est_en_francais():
    assert dt.LABELS[dt.PRECONDITION_NON_REMPLIE] == "Prérequis non rempli (environnement)"
    assert dt.PRECONDITION_NON_REMPLIE in dt.CATEGORIES


# ── 3. Réparation : un prérequis n'est jamais réparé automatiquement ────────────────────────

def test_un_prerequis_non_rempli_n_est_jamais_envoye_en_reparation_automatique():
    echecs = [_assertion("given", "le module est installé")]

    diagnostic = do.diagnose(echecs)
    decision = evaluate(CircuitState(max_iterations=5, stall_limit=3), echecs)

    assert diagnostic.cause_category == dt.PRECONDITION_NON_REMPLIE
    assert diagnostic.defect_origin == do.INDETERMINE
    assert decision.should_continue is False, "budget disponible, mais aucune réparation"


def test_un_hook_en_echec_n_est_jamais_envoye_en_reparation_automatique():
    echec = BehaveFailure("s", "", "hook", "", raw="RuntimeError: connexion refusée",
                          step_type=STEP_TYPE_HOOK)

    decision = evaluate(CircuitState(max_iterations=5, stall_limit=3), [echec])

    assert decision.should_continue is False


def test_une_assertion_dans_une_action_reste_reparable_test_cassé():
    """D2 : c'est le TEST qui est faux — la réparation reste autorisée, contrairement au prérequis."""
    decision = evaluate(CircuitState(max_iterations=5, stall_limit=3), [_assertion("when")])

    assert decision.should_continue is True
