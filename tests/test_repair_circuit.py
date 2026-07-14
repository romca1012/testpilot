"""§6 — disjoncteur de réparation : les trois signaux de coupure + le comptage de progrès.

Point central : le signal métier (origine du défaut, livré par le pilier verdict) prime.
Un ``vrai_bug`` se remonte tel quel, un ``indetermine`` exige une confirmation humaine, et
seul un ``test_a_reparer`` autorise de nouvelles tentatives — jusqu'à ce que le stall ou le
plafond d'itérations coupe.
"""

from testpilot.execution.behave_result import BehaveFailure
from testpilot.guardrails import repair_circuit as rc


def _assertion_fail():   # cause assertion_mismatch → vrai_bug
    return [BehaveFailure("cas A", "le total", "assertion", "AssertionError: attendu 0, obtenu 5")]


def _timeout_fail():     # cause wrong_field_name → test_a_reparer
    return [BehaveFailure("cas A", "je clique", "ui_timeout", "TimeoutError: locator introuvable")]


def _unknown_fail():     # cause unknown → indetermine
    return [BehaveFailure("cas A", "étape", "mystere", "rien d'exploitable")]


# --- Signature d'échec ----------------------------------------------------------

def test_signature_stable_pour_meme_echec_et_vide_sans_echec():
    assert rc.failure_signature(_timeout_fail()) == rc.failure_signature(_timeout_fail())
    assert rc.failure_signature([]) == ""


def test_signature_distingue_des_echecs_differents():
    assert rc.failure_signature(_timeout_fail()) != rc.failure_signature(_assertion_fail())


# --- Résolution -----------------------------------------------------------------

def test_plus_aucun_echec_arrete_en_resolved():
    d = rc.evaluate(rc.CircuitState(), [])
    assert d.should_continue is False
    assert d.outcome == rc.RESOLVED


# --- Le signal métier prime -----------------------------------------------------

def test_vrai_bug_arrete_sans_reparer():
    d = rc.evaluate(rc.CircuitState(), _assertion_fail())
    assert d.should_continue is False
    assert d.outcome == rc.REAL_BUG
    assert d.defect_verdict.defect_origin == "vrai_bug"


def test_indetermine_arrete_pour_confirmation_humaine():
    d = rc.evaluate(rc.CircuitState(), _unknown_fail())
    assert d.should_continue is False
    assert d.outcome == rc.NEEDS_CONFIRMATION
    assert d.defect_verdict.requires_human_confirmation is True


def test_test_a_reparer_autorise_une_nouvelle_tentative():
    d = rc.evaluate(rc.CircuitState(), _timeout_fail())
    assert d.should_continue is True
    assert d.outcome == rc.CONTINUE
    assert d.defect_verdict.defect_origin == "test_a_reparer"


# --- Caps de sécurité (uniquement sur un test_a_reparer) ------------------------

def test_stall_coupe_apres_tentatives_identiques_consecutives():
    state = rc.CircuitState(stall_limit=3, max_iterations=25)
    sig = rc.failure_signature(_timeout_fail())
    # Deux tentatives identiques : pas encore le stall.
    state.record(sig)
    state.record(sig)
    assert rc.evaluate(state, _timeout_fail()).should_continue is True
    # Troisième tentative identique : plus de progrès → coupure.
    state.record(sig)
    d = rc.evaluate(state, _timeout_fail())
    assert d.should_continue is False
    assert d.outcome == rc.STALLED


def test_un_echec_different_relance_le_compteur_de_progres():
    state = rc.CircuitState(stall_limit=3)
    sig1 = rc.failure_signature(_timeout_fail())
    state.record(sig1)
    state.record(sig1)  # repeat_count = 2
    state.record("autre_signature")  # progrès → reset à 1
    assert state.repeat_count == 1
    assert state.stalled is False


def test_plafond_iterations_prime_sur_le_stall():
    # max_iterations bas, stall_limit haut : c'est le plafond dur qui coupe en premier.
    state = rc.CircuitState(stall_limit=10, max_iterations=2)
    sig = rc.failure_signature(_timeout_fail())
    state.record(sig)
    state.record(sig)  # iterations = 2 == max
    d = rc.evaluate(state, _timeout_fail())
    assert d.should_continue is False
    assert d.outcome == rc.MAX_ITERATIONS_REACHED


def test_vrai_bug_prime_meme_au_plafond_iterations():
    # Un vrai bug se remonte comme tel, pas comme un épuisement d'itérations.
    state = rc.CircuitState(max_iterations=1)
    state.record("x")
    d = rc.evaluate(state, _assertion_fail())
    assert d.outcome == rc.REAL_BUG


def test_record_incremente_les_iterations():
    state = rc.CircuitState()
    state.record("a")
    state.record("a")
    state.record("b")
    assert state.iterations == 3
