"""§5 asymétrique — origine du défaut et régime de confirmation humaine.

« test à réparer » et « indéterminé » exigent une confirmation humaine ; « vrai bug »
se remonte directement (faux positif acceptable, faux négatif inacceptable).
"""

from testpilot.execution.behave_result import BehaveFailure
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt


def test_business_assertion_is_direct_bug_no_confirmation():
    origin = do.classify_defect_origin(dt.ASSERTION_MISMATCH)
    assert origin == do.VRAI_BUG
    assert do.confirmation_for(origin) == do.NOT_REQUIRED


def test_technical_cause_needs_human_confirmation():
    """Causes techniques ADOSSÉES À UN SIGNAL → réparables, mais jamais sans confirmation.

    `MISSING_SERVER_CONTEXT` a QUITTÉ cette liste en 0015 : aucun type d'exception ne la
    produit, elle ne vient que de mots-clés — voir le test dédié ci-dessous.
    """
    for cause in (dt.WRONG_NAVIGATION, dt.WRONG_FIELD_NAME, dt.MISSING_ROLE,
                  dt.BROKEN_TEST_CODE):
        origin = do.classify_defect_origin(cause)
        assert origin == do.TEST_A_REPARER
        assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_missing_server_context_est_une_voie_degradee():
    """Arbitrage 0015 Q4 : cette cause INFORME, elle ne décide jamais de la réparabilité.

    Elle est réelle et documentée, mais elle ne peut venir que d'un TEXTE (aucune exception ne
    la produit) : la faire pointer vers `test_a_reparer` autoriserait la boucle 0014 sur une
    simple correspondance de mots. D'où `indetermine` → un humain tranche.
    """
    origin = do.classify_defect_origin(dt.MISSING_SERVER_CONTEXT)
    assert origin == do.INDETERMINE
    assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_unknown_defaults_to_confirmation():
    origin = do.classify_defect_origin(dt.UNKNOWN)
    assert origin == do.INDETERMINE
    assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_diagnose_timeout_run_is_test_to_repair_pending():
    failures = [BehaveFailure("s", "je clique", "ui_timeout", "TimeoutError: locator")]
    verdict = do.diagnose(failures)
    assert verdict.defect_origin == do.TEST_A_REPARER
    assert verdict.requires_human_confirmation is True


def test_diagnose_assertion_run_is_direct_bug():
    failures = [BehaveFailure("s", "le total", "assertion", "AssertionError: attendu 0")]
    verdict = do.diagnose(failures)
    assert verdict.defect_origin == do.VRAI_BUG
    assert verdict.requires_human_confirmation is False


def test_diagnose_no_failures_returns_none():
    assert do.diagnose([]) is None


# ── Lot 09 (C9) — vérifié, pas supposé : `blocked`/`aucun_constat` n'ouvrent jamais la boucle ────
#
# Le brief du lot demandait de VÉRIFIER que ces deux causes n'entrent jamais dans la réparation
# automatique — c'était déjà vrai dans le code (`defect_origin._ORIGIN_BY_CAUSE`), mais AUCUN test
# ne le prouvait avant ce lot. Ajoutés ici plutôt que supposés sur lecture seule du code.

def test_precondition_non_remplie_exige_une_confirmation_jamais_une_reparation():
    """`blocked` (lot 02, D1) — un prérequis manquant est un problème d'ENVIRONNEMENT, jamais un
    test à réparer : la boucle 0014 ne doit jamais s'ouvrir dessus."""
    origin = do.classify_defect_origin(dt.PRECONDITION_NON_REMPLIE)
    assert origin == do.INDETERMINE
    assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_aucun_constat_exige_une_confirmation_jamais_une_reparation():
    """Lot 03 (D3) — un scénario vert qui n'a rien prouvé n'est pas un « échec technique » que
    réécrire corrigerait : réparer un `.feature` qui ne vérifie rien n'a pas de sens."""
    origin = do.classify_defect_origin(dt.AUCUN_CONSTAT)
    assert origin == do.INDETERMINE
    assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_diagnose_une_precondition_manquante_via_un_hook_est_indetermine():
    """Round-trip réaliste : un `PreconditionNonRemplieError` levé dans un hook (`step_type` du
    JSON Behave, jamais le texte de l'agent — décision 0015) doit produire ce même résultat via
    `classify_failure` → `diagnose`, pas seulement via la constante testée isolément ci-dessus."""
    failures = [BehaveFailure("cas A", "before_scenario", "erreur",
                              "PreconditionNonRemplieError: la page n'a pas pu être lue",
                              step_type="hook")]
    verdict = do.diagnose(failures)
    assert verdict.defect_origin == do.INDETERMINE
    assert verdict.requires_human_confirmation is True
