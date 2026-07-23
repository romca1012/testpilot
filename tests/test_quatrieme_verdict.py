"""§2bis — le 4ᵉ verdict `donnee_invalide` : « le test a tourné, mais SA donnée a été refusée ».

⚠️ Le défaut fermé : ces cas levaient une `AssertionError` → Behave « ASSERT FAILED: » →
taxonomie `assertion_mismatch` → verdict **`non_conforme`**. On accusait l'application à tort (4
des 6 faux verdicts de la re-mesure). Une exception DÉDIÉE (`DonneeRefuseeError`, sous-classe de
`ValueError`) survit à la taxonomie et se projette sur `donnee_invalide` — l'app n'est plus accusée.
"""

from __future__ import annotations

from testpilot.execution.behave_result import BehaveFailure, BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st


def _fail(*, tb="", raw="", ftype=""):
    return BehaveFailure(scenario_name="s", step_text="", failure_type=ftype,
                         traceback_summary=tb, raw=raw)


# ── Taxonomie : la classe dédiée → DONNEE_REFUSEE ─────────────────────────────

def test_l_exception_dediee_est_classee_donnee_refusee():
    """Comme `InvalidOptionValueError` (0019) : le nom de classe (survit en run réel via le
    formatter) est le signal décisif."""
    f = _fail(raw="_base_helpers.DonneeRefuseeError: LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire.")
    assert dt.classify_failure(f) == dt.DONNEE_REFUSEE


def test_le_filet_mots_cles_rattrape_si_le_nom_de_classe_manque():
    """Belt-and-suspenders : même sans nom de classe identifiable (et hors ASSERT FAILED),
    une phrase très spécifique du message suffit."""
    f = _fail(raw="échec : le navigateur a refusé d'envoyer, jeu de données du test irrecevable")
    assert dt.classify_failure(f) == dt.DONNEE_REFUSEE


def test_une_vraie_assertion_metier_reste_non_conforme():
    """Garde négative : une assertion métier normale ne doit PAS tomber en donnee_refusee."""
    f = _fail(raw="ASSERT FAILED: total attendu 0, obtenu 5")
    assert dt.classify_failure(f) == dt.ASSERTION_MISMATCH


# ── Statut : projection + agrégation ──────────────────────────────────────────

def _outcome(scenarios, failures):
    real = BehaveResult(success=True, returncode=0, scenarios=scenarios, failures=failures)
    return ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=real)


_RAW_REFUS = "_base_helpers.DonneeRefuseeError: LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire."


def test_donnee_refusee_donne_execution_success_et_fonctionnel_donnee_invalide():
    """Le cœur : le test a TOURNÉ (success) ; c'est sa donnée qui est en cause (donnee_invalide),
    surtout PAS l'application (non_conforme)."""
    scen = [BehaveScenario("[Nominal] créer", "failed", error="DonneeRefuseeError")]
    fails = [BehaveFailure("[Nominal] créer", "Alors un enregistrement existe", "unknown",
                           "", raw=_RAW_REFUS)]
    v = st.derive_verdict(_outcome(scen, fails))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_DONNEE_INVALIDE


def test_donnee_invalide_surface_AU_DESSUS_du_conforme():
    """Un scénario dont la donnée a été refusée n'a rien pu prouver : il ne doit pas être masqué
    par les scénarios verts."""
    scen = [BehaveScenario("[Nominal] ok", "passed"),
            BehaveScenario("[Limite] refus", "failed", error="DonneeRefuseeError")]
    fails = [BehaveFailure("[Limite] refus", "Alors créé", "unknown", "", raw=_RAW_REFUS)]
    v = st.derive_verdict(_outcome(scen, fails))
    assert v.functional_status == st.FUNC_DONNEE_INVALIDE
    assert v.execution_status == st.EXEC_SUCCESS, "le test a bien tourné techniquement"


def test_non_conforme_surface_AU_DESSUS_de_donnee_invalide():
    """Précédence : un vrai défaut applicatif (non_conforme) prime sur une donnée invalide."""
    scen = [BehaveScenario("[Erreur] métier", "failed", error="AssertionError"),
            BehaveScenario("[Limite] refus", "failed", error="DonneeRefuseeError")]
    fails = [BehaveFailure("[Erreur] métier", "Alors total 0", "assertion",
                           "ASSERT FAILED: attendu 0, obtenu 5"),
             BehaveFailure("[Limite] refus", "Alors créé", "unknown", "", raw=_RAW_REFUS)]
    v = st.derive_verdict(_outcome(scen, fails))
    assert v.functional_status == st.FUNC_NON_CONFORME


# ── Raffinement `agence` : test non constructible → indetermine, PAS non_conforme ─────────────

_RAW_RESOLVEUR = ("_base_helpers.ResolveurIncompletError: résolveur: champ requis 'agence' non "
                  "synthétisable (select sans option sélectionnable).")


def test_resolveur_incomplet_est_technical_error_indetermine():
    """⚠️ Le raffinement. Quand le résolveur ne peut pas construire le test (select `agence` vide),
    le verdict est `technical_error / indetermine` — l'application n'est ni jugée ni ACCUSÉE.
    Avant, une `AssertionError` le faisait tomber en `non_conforme` (fausse accusation)."""
    scen = [BehaveScenario("[Nominal] créer", "failed", error="ResolveurIncompletError")]
    fails = [BehaveFailure("[Nominal] créer", "Quand je remplis le formulaire", "unknown", "",
                           raw=_RAW_RESOLVEUR)]
    v = st.derive_verdict(_outcome(scen, fails))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE
    assert v.functional_status != st.FUNC_NON_CONFORME, "ne JAMAIS accuser l'app non observée"


def test_resolveur_incomplet_classe_et_n_est_pas_repare_automatiquement():
    """La cause dédiée est reconnue ET n'autorise PAS la réparation auto (0014) : réécrire le
    Gherkin ne remplirait pas un select vide — un humain doit trancher."""
    from testpilot.verdict import defect_origin as do
    f = BehaveFailure("s", "", "unknown", "", raw=_RAW_RESOLVEUR)
    assert dt.classify_failure(f) == dt.RESOLVEUR_INCOMPLET
    assert do.classify_defect_origin(dt.RESOLVEUR_INCOMPLET) == do.INDETERMINE
    assert do.confirmation_for(do.INDETERMINE) == do.PENDING_HUMAN  # confirmation humaine requise
