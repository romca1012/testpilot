"""INVARIANT CRITIQUE §5 — les deux axes de statut sont indépendants et jamais confondus.

Le point capital : un échec d'assertion métier donne exécution=success MAIS
fonctionnel=non_conforme (le test a tourné, l'app répond faux) ; et un non_conforme
n'est JAMAIS masqué par des échecs techniques concomitants.
"""

from testpilot.execution.behave_result import BehaveFailure, BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import status as st


def _outcome(scenarios, failures, dry_ok=True, returncode=0):
    real = BehaveResult(success=(returncode == 0), returncode=returncode,
                        scenarios=scenarios, failures=failures)
    return ExecutionOutcome(module_name="m", dry_run_passed=dry_ok,
                            real_run=real if dry_ok else None)


def test_passing_scenario_is_success_and_conforme():
    v = st.derive_verdict(_outcome([BehaveScenario("[Nominal] ok", "passed")], []))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_CONFORME


def test_business_assertion_failure_is_success_but_non_conforme():
    """Indépendance des axes : a TOURNÉ (success) mais comportement FAUX (non_conforme)."""
    scenarios = [BehaveScenario("[Erreur] montant", "failed", error="AssertionError")]
    failures = [BehaveFailure("[Erreur] montant", "Alors le total vaut 0", "assertion",
                              "AssertionError: attendu 0, obtenu 5")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_NON_CONFORME


def test_technical_failure_is_technical_error_and_indetermine():
    scenarios = [BehaveScenario("[Nominal]", "failed", error="TimeoutError")]
    failures = [BehaveFailure("[Nominal]", "Quand je clique", "ui_timeout",
                              "TimeoutError: locator not found")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_non_conforme_is_never_masked_by_technical_failure():
    """Un vrai constat produit surface même si un autre scénario casse techniquement."""
    scenarios = [
        BehaveScenario("[Erreur] métier", "failed", error="AssertionError"),
        BehaveScenario("[Nominal] technique", "failed", error="TimeoutError"),
    ]
    failures = [
        BehaveFailure("[Erreur] métier", "Alors erreur affichée", "assertion", "AssertionError: x"),
        BehaveFailure("[Nominal] technique", "Quand je vais", "ui_timeout", "TimeoutError: y"),
    ]
    v = st.derive_verdict(_outcome(scenarios, failures))
    # Exécution dégradée par la panne technique, MAIS le fonctionnel reste non_conforme.
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_NON_CONFORME


def test_mixed_pass_and_business_failure_is_success_non_conforme():
    scenarios = [
        BehaveScenario("[Nominal] ok", "passed"),
        BehaveScenario("[Erreur] métier", "failed", error="AssertionError"),
    ]
    failures = [BehaveFailure("[Erreur] métier", "Alors x", "assertion", "AssertionError: z")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_NON_CONFORME
    assert v.scenarios_passed == 1 and v.scenarios_failed == 1


def test_failed_dry_run_is_technical_error_indetermine():
    v = st.derive_verdict(ExecutionOutcome("m", dry_run_passed=False, real_run=None))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_subprocess_crash_is_technical_error():
    v = st.derive_verdict(_outcome([], [], dry_ok=True, returncode=-2))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_crash_a_code_de_retour_POSITIF_sans_scenario_est_technical_error_pas_untested():
    """B4 (audit 2026-08-07) — un crash « normal » de Python (exception non rattrapée dans notre
    formatter JSON maison, process tué par disque plein, etc.) ressort avec un code de retour
    POSITIF, pas négatif (réservé aux sentinelles internes du runner). Avant ce correctif,
    `aggregate([])` rendait `not_executed/not_evaluated` — projeté en « untested » à l'écran,
    comme si le test n'avait JAMAIS tourné, alors qu'il a réellement tourné et planté."""
    v = st.derive_verdict(_outcome([], [], dry_ok=True, returncode=1))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE
    # `indetermine` + un axe exécution qui n'est PAS `not_executed` → « retest », jamais
    # « untested » : c'est exactement la distinction que ce correctif rétablit.
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_RETEST
    assert st.statut_de_test(v.execution_status, v.functional_status) != st.STATUT_UNTESTED


def test_returncode_non_nul_AVEC_au_moins_un_scenario_reste_un_echec_fonctionnel_normal():
    """Ne pas confondre avec l'échec fonctionnel ORDINAIRE : Behave ressort aussi non-zéro quand
    un scénario échoue légitimement — tant qu'au moins un scénario est bien rapporté, ce n'est
    PAS un crash, la garde du B4 ne doit donc jamais s'y appliquer."""
    scenarios = [BehaveScenario("[Erreur] montant", "failed", error="AssertionError")]
    failures = [BehaveFailure("[Erreur] montant", "Alors le total vaut 0", "assertion",
                              "AssertionError: attendu 0, obtenu 5")]
    v = st.derive_verdict(_outcome(scenarios, failures, returncode=1))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_NON_CONFORME


# ── Confiance du verdict selon le connecteur (étape 2.2 du plan de consolidation) ───────────────
#
# GenericWebConnector n'a aucune méthode RPC (get_schema/search/read lèvent NotImplementedError) :
# un cas générique ne peut vérifier que ce que l'UI affiche, jamais une vérité côté base de données
# comme un cas Odoo. Ce champ étiquette cette différence, il ne la crée pas.

def test_sans_connector_type_le_verdict_reste_backend_verified():
    """Comportement HISTORIQUE inchangé pour tout appelant qui ne fournit pas ce paramètre
    (cli.py, repair_service.py) — même repli que `connectors/factory.py::build_connector`."""
    v = st.derive_verdict(_outcome([BehaveScenario("[Nominal] ok", "passed")], []))
    assert v.ground_truth == st.GROUND_TRUTH_BACKEND_VERIFIED


def test_connector_type_odoo_est_backend_verified():
    v = st.derive_verdict(
        _outcome([BehaveScenario("[Nominal] ok", "passed")], []), connector_type="odoo")
    assert v.ground_truth == st.GROUND_TRUTH_BACKEND_VERIFIED


def test_connector_type_web_est_ui_only():
    v = st.derive_verdict(
        _outcome([BehaveScenario("[Nominal] ok", "passed")], []), connector_type="web")
    assert v.ground_truth == st.GROUND_TRUTH_UI_ONLY


def test_un_connector_type_inconnu_est_traite_comme_ui_only():
    """Prudent par défaut : seul `odoo` est reconnu comme disposant d'une vérité de référence —
    un type non reconnu ne doit jamais hériter silencieusement de cette confiance-là."""
    v = st.derive_verdict(
        _outcome([BehaveScenario("[Nominal] ok", "passed")], []), connector_type="sap")
    assert v.ground_truth == st.GROUND_TRUTH_UI_ONLY


def test_le_ground_truth_est_pose_meme_sur_un_echec_technique_precoce():
    """Le connecteur est déjà connu avant même qu'un scénario tourne (dry-run raté, crash) — le
    champ ne doit pas rester au défaut par accident sur ces chemins de sortie précoce."""
    v = st.derive_verdict(
        ExecutionOutcome("m", dry_run_passed=False, real_run=None), connector_type="web")
    assert v.ground_truth == st.GROUND_TRUTH_UI_ONLY


def test_aggregate_calcule_aussi_le_ground_truth_pour_un_appel_direct():
    """`aggregate` est appelable directement (hors `derive_verdict`) — le paramètre doit s'y
    comporter à l'identique, pas seulement via son unique appelant de production."""
    v = st.aggregate([st.ScenarioVerdict("s", st.EXEC_SUCCESS, st.FUNC_CONFORME)],
                     connector_type="web")
    assert v.ground_truth == st.GROUND_TRUTH_UI_ONLY


def test_returncode_zero_sans_scenario_reste_le_comportement_d_avant():
    """Une feature sans le moindre scénario (fichier vide) ressort en `0` — cas légitime, distinct
    du crash B4 (qui suppose un `returncode` NON nul) : comportement inchangé."""
    v = st.derive_verdict(_outcome([], [], returncode=0))
    assert v.execution_status == st.EXEC_NOT_EXECUTED
    assert v.functional_status == st.FUNC_NOT_EVALUATED


def test_axes_are_independent_all_combinations_reachable():
    """Les quatre combinaisons utiles (success/tech × conforme/non_conforme/indetermine)."""
    green = st.derive_verdict(_outcome([BehaveScenario("a", "passed")], []))
    bug = st.derive_verdict(_outcome([BehaveScenario("b", "failed", error="AssertionError")],
                                     [BehaveFailure("b", "s", "assertion", "AssertionError")]))
    broken = st.derive_verdict(_outcome([BehaveScenario("c", "failed", error="Timeout")],
                                        [BehaveFailure("c", "s", "ui_timeout", "TimeoutError")]))
    combos = {(green.execution_status, green.functional_status),
              (bug.execution_status, bug.functional_status),
              (broken.execution_status, broken.functional_status)}
    assert (st.EXEC_SUCCESS, st.FUNC_CONFORME) in combos
    assert (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME) in combos
    assert (st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE) in combos
