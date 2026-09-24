"""Lot 02 — la bibliothèque de steps ne signale plus un PRÉREQUIS par une `AssertionError`.

Avant : « le module Odoo est installé », « la session RPC est initialisée », « l'utilisateur est
authentifié », « aucun enregistrement ne commence par … » levaient `AssertionError` → « ASSERT FAILED »
→ `non_conforme` — un bug applicatif présumé, alors que c'est l'ENVIRONNEMENT qui ne remplit pas le
prérequis (cas 101 tirage 1 du lot 12, F2). Maintenant : `PreconditionNonRemplieError` → `blocked`.

Chaque test prouve les DEUX sens (falsifiabilité) : le prérequis rempli laisse passer, non rempli
lève la bonne exception — et jamais une `AssertionError`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _base_helpers as helpers
    import _odoo_background_steps as background
    import _odoo_steps as odoo_steps
    return helpers, background, odoo_steps


class _Modele:
    def __init__(self, ids=(), champs=("name",)):
        self._ids, self._champs = list(ids), champs

    def search(self, *_a, **_k):
        return self._ids

    def fields_get(self, *_a, **_k):
        return {c: {} for c in self._champs}


class _Env(dict):
    def __init__(self, modeles, uid):
        super().__init__(modeles)
        self.uid = uid


def _contexte(*, uid=7, modeles=None, odoo=True):
    env = _Env(modeles or {}, uid)
    return types.SimpleNamespace(odoo=types.SimpleNamespace(env=env) if odoo else None)


# ── Contexte : session, utilisateur, module ─────────────────────────────────────────────────

def test_session_rpc_absente_est_un_prerequis_non_rempli():
    helpers, background, _ = _charger()

    with pytest.raises(helpers.PreconditionNonRemplieError, match="session OdooRPC"):
        background.step_odoo_accessible(_contexte(odoo=False))

    background.step_odoo_accessible(_contexte())  # rempli : passe


def test_utilisateur_non_authentifie_est_un_prerequis_non_rempli():
    helpers, background, _ = _charger()

    with pytest.raises(helpers.PreconditionNonRemplieError, match="pas authentifié"):
        background.step_authenticated(_contexte(uid=False))

    background.step_authenticated(_contexte(uid=7))


def test_module_non_installe_est_un_prerequis_non_rempli_jamais_une_assertion():
    """Le cas 101 tirage 1 (F2) : l'agent avait inventé « le module … est installé »."""
    helpers, background, _ = _charger()
    absent = _contexte(modeles={"ir.module.module": _Modele(ids=[])})
    present = _contexte(modeles={"ir.module.module": _Modele(ids=[42])})

    with pytest.raises(helpers.PreconditionNonRemplieError, match="pas installé") as info:
        background.step_module_installed(absent, "pilote_p1_c101_i1_x")
    assert not isinstance(info.value, AssertionError)

    background.step_module_installed(present, "base")


def test_donnees_residuelles_sont_un_prerequis_non_rempli():
    helpers, _, odoo_steps = _charger()

    with pytest.raises(helpers.PreconditionNonRemplieError, match="résiduels"):
        odoo_steps.step_no_test_records(
            _contexte(modeles={"helpdesk.ticket": _Modele(ids=[3, 4])}), "AUTOTEST", "helpdesk.ticket")

    odoo_steps.step_no_test_records(
        _contexte(modeles={"helpdesk.ticket": _Modele(ids=[])}), "AUTOTEST", "helpdesk.ticket")


def test_une_verification_impossible_reste_un_simple_avertissement_pas_un_prerequis(capsys):
    """Comportement historique CONSERVÉ : si la vérification pré-test elle-même est impossible
    (modèle inconnu), c'est un WARN — jamais un blocage. Et l'exception de prérequis, elle, n'est
    PAS avalée par ce `except Exception` (elle est levée hors du `try`)."""
    _, _, odoo_steps = _charger()

    odoo_steps.step_no_test_records(_contexte(modeles={}), "AUTOTEST", "modele.inconnu")

    assert "Vérification pré-test impossible" in capsys.readouterr().err


# ── Then : « cet enregistrement » sans step précédent = bug du TEST ─────────────────────────

@pytest.mark.parametrize("appel", [
    lambda s, c: s.step_field_equals(c, "name", "res.partner", "x"),
    lambda s, c: s.step_field_equals_simple(c, "name", "x"),
    lambda s, c: s.step_field_not_empty(c, "name"),
    lambda s, c: s.step_field_m2o_equals(c, "partner_id", "res.partner", "x"),
    lambda s, c: s.step_field_m2o_contains(c, "partner_id", "x"),
])
def test_un_step_qui_suppose_un_enregistrement_absent_leve_runtime_error_pas_assertion(appel):
    _, _, odoo_steps = _charger()
    contexte = _contexte()  # ni `last_record_ids` ni `last_record_model`

    with pytest.raises(RuntimeError) as info:
        appel(odoo_steps, contexte)

    assert not isinstance(info.value, AssertionError), "un bug du test n'est pas un constat"
    assert "Aucun enregistrement en contexte" in str(info.value)


def test_un_vrai_ecart_de_valeur_reste_une_assertion():
    """Non-régression : le CONSTAT (`Alors`) reste une `AssertionError`, donc `non_conforme`."""
    _, _, odoo_steps = _charger()

    class _Enregistrement:
        def read(self, champs):
            return [{champs[0]: "reel"}]

    class _ModeleLu:
        def browse(self, _id):
            return _Enregistrement()

    contexte = _contexte(modeles={"res.partner": _ModeleLu()})
    contexte.last_record_ids, contexte.last_record_model = [1], "res.partner"

    with pytest.raises(AssertionError, match="attendu 'autre', obtenu 'reel'"):
        odoo_steps.step_field_equals_simple(contexte, "name", "autre")


# ── La classification en bout de chaîne : ce que Behave écrira réellement ───────────────────

def test_l_erreur_de_prerequis_est_classee_blocked_au_type_meme_dans_un_when():
    """Le TYPE d'exception suffit : même placée (à tort) sous un `Quand`, elle reste un prérequis."""
    from testpilot.execution.behave_result import BehaveFailure
    from testpilot.verdict import defect_taxonomy as dt

    echec = BehaveFailure("s", "", "unknown", "",
                          raw="Traceback (most recent call last):\n  ...\n"
                              "PreconditionNonRemplieError: Le module Odoo 'x' n'est pas installé.",
                          step_type="when")

    assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE
