"""Lot VH-02 — un constat doit pouvoir être faux, et un constat échoué ne peut pas être oublié (V1, V10, audit 2026-10-08).

V1 : `constater(page.locator(".succes"))` réussissait toujours (un objet sans `__bool__` ni `__len__` est vrai en Python) et
le scénario sortait `conforme` sans rien vérifier. V10 : un constat échoué rattrapé par `except (AssertionError, X): pass`
passait la garde d'écriture, et un AUTRE constat réussi suffisait à rendre le scénario `conforme`.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.execution import behave_result as br
from testpilot.generation.tools import write
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _base_helpers as H  # noqa: E402


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    chemin = tmp_path / "constats.jsonl"
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(chemin))
    H.definir_etat_constat(scenario="S", step_type="then")
    return lambda: [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []


class _LocatorPlaywright:
    """Double fidèle : même module que la vraie classe, et comme elle, ni `__bool__` ni `__len__`."""


_LocatorPlaywright.__module__ = "playwright.sync_api._generated"


class _Element:
    def is_visible(self):
        return False


# ── V1 : une condition toujours vraie n'est pas un constat ────────────────────────────────────────────────


@pytest.mark.parametrize("condition", [
    _LocatorPlaywright(),            # constater(page.locator(".succes"))
    _Element().is_visible,           # méthode NON appelée : toujours vraie, même si l'élément est invisible
    object(),                        # objet de vérité par défaut
    lambda: False,
])
def test_falsifiable_une_condition_qui_ne_prouve_rien_est_refusee_et_laisse_un_constat_echoue(condition, sidecar):
    """Le constat ÉCHOUÉ consigné est ce qui rattrape un refus avalé par le code du test (revue VH-02)."""
    with pytest.raises(H.ConstatInvalideError, match="ne prouve rien"):
        H.constater(condition, "le message de succès est affiché")

    assert [c["ok"] for c in sidecar()] == [False]


def test_falsifiable_un_refus_avale_par_le_test_ne_peut_pas_donner_conforme(sidecar):
    """Revue VH-02 : un helper non décoré avale le refus (`except Exception: pass`) ; un autre constat réussit."""
    try:
        H.constater(_LocatorPlaywright(), "succès affiché")
    except Exception:
        pass
    H.constater(True, "url")
    scenario = br.BehaveScenario(name="S", status="passed", duration=1.0)
    resultat = br.BehaveResult(success=True, returncode=0, dry_run=False)
    resultat.scenarios = [scenario]

    br.rattacher_constats(resultat, sidecar())

    assert st.scenario_verdict(scenario, []).functional_status == st.FUNC_INDETERMINE


def test_une_date_odoo_reste_une_condition_falsifiable(sidecar):
    """Un champ Date Odoo vaut une date quand il est rempli, `False` sinon : il ne doit pas être refusé."""
    import datetime

    H.constater(datetime.date(2026, 10, 8), "date renseignée")
    H.constater(datetime.datetime(2026, 10, 8, 12, 0), "date et heure renseignées")

    assert [c["ok"] for c in sidecar()] == [True, True]


def test_le_refus_est_une_erreur_du_test_pas_un_echec_de_l_application():
    assert issubclass(H.ConstatInvalideError, TypeError) and not issubclass(H.ConstatInvalideError, AssertionError)
    echec = br.BehaveFailure(scenario_name="S", step_text="Alors x", failure_type="error", traceback_summary="",
                             raw="\n".join(["Traceback",
                                            "_base_helpers.ConstatInvalideError: Constat invalide : un objet Playwright (Locator)"]),
                             step_type="then")
    # Le mot « Locator » du message ne doit pas le faire passer pour un sélecteur introuvable : c'est le code du test.
    assert dt.dominant_category([echec]) == dt.BROKEN_TEST_CODE


@pytest.mark.parametrize("condition, attendu", [
    (True, True), (False, False), (1, True), (0, False), (Decimal("0.00"), False), ("x", True), ("", False),
    ([1], True), ([], False), ({}, False), (None, False), (re.search("a", "abc"), True), (re.search("z", "abc"), False),
])
def test_les_conditions_qui_peuvent_etre_fausses_restent_acceptees(condition, attendu, sidecar):
    if attendu:
        H.constater(condition, "m")
    else:
        with pytest.raises(AssertionError):
            H.constater(condition, "m")

    assert sidecar()[-1]["ok"] is attendu


def test_aucun_appel_de_la_bibliotheque_ne_passe_une_condition_toujours_vraie():
    """Garde-fou de non-régression : relire tous les `constater(` de la bibliothèque — aucun ne passe un Locator ni une méthode."""
    import inspect

    sources = (config.BEHAVE_RUNTIME_DIR / "steps_library").rglob("*.py")
    suspects = []
    for chemin in sources:
        for noeud in ast.walk(ast.parse(chemin.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "constater" and noeud.args:
                cond = noeud.args[0]
                if isinstance(cond, ast.Call) and getattr(cond.func, "attr", "") in {"locator", "get_by_role", "get_by_text",
                                                                                     "get_by_label", "query_selector"}:
                    suspects.append(f"{chemin.name}:{noeud.lineno}")
                if isinstance(cond, ast.Attribute) and cond.attr in {"is_visible", "is_enabled", "is_checked"}:
                    suspects.append(f"{chemin.name}:{noeud.lineno}")
    assert not suspects and inspect is not None, suspects


# ── V10 : un constat échoué dans un scénario passé ────────────────────────────────────────────────────────


def _resultat(constats):
    resultat = br.BehaveResult(success=True, returncode=0, dry_run=False)
    resultat.scenarios = [br.BehaveScenario(name="S", status="passed", duration=1.0)]
    br.rattacher_constats(resultat, constats)
    return resultat.scenarios[0]


def test_falsifiable_un_constat_echoue_avale_n_est_jamais_rachete_par_un_autre_constat_reussi():
    scenario = _resultat([{"scenario": "S", "step_type": "then", "ok": False},
                          {"scenario": "S", "step_type": "then", "ok": True}])

    verdict = st.scenario_verdict(scenario, [])

    assert scenario.constats_echoues == 1
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert verdict.cause_category == dt.CONSTAT_ECHOUE_IGNORE


def test_un_constat_echoue_sous_un_quand_compte_aussi():
    scenario = _resultat([{"scenario": "S", "step_type": "when", "ok": False},
                          {"scenario": "S", "step_type": "then", "ok": True}])

    assert st.scenario_verdict(scenario, []).functional_status == st.FUNC_INDETERMINE


def test_sans_constat_echoue_le_verdict_ne_change_pas():
    scenario = _resultat([{"scenario": "S", "step_type": "then", "ok": True}])

    assert st.scenario_verdict(scenario, []).functional_status == st.FUNC_CONFORME
    hors_runner = br.BehaveScenario(name="S", status="passed", duration=1.0)  # mécanisme absent : comportement historique
    assert st.scenario_verdict(hors_runner, []).functional_status == st.FUNC_CONFORME


def test_la_cause_a_un_libelle_francais_et_une_origine_prudente():
    from testpilot.verdict import defect_origin

    assert dt.LABELS[dt.CONSTAT_ECHOUE_IGNORE] == "Une vérification a échoué sans faire échouer le test"
    assert defect_origin.classify_defect_origin(dt.CONSTAT_ECHOUE_IGNORE) == defect_origin.INDETERMINE


# ── V10 : la garde d'écriture voit les tuples ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("clause", ["except (AssertionError, ValueError):", "except (ValueError, Exception):",
                                    "except TypeError:", "except ConstatInvalideError:"])
def test_falsifiable_un_except_en_tuple_qui_avale_l_echec_est_refuse(clause):
    code = (
        "from behave import then\n"
        "from _base_helpers import constater\n"
        "@then('le total vaut \"{v}\"')\n"
        "def step(context, v):\n"
        "    try:\n"
        "        constater(context.page.inner_text('#total') == v, 'total')\n"
        f"    {clause}\n"
        "        pass\n")

    assert write._forbidden_assertion_placement(ast.parse(code)) != ""


def test_un_except_en_tuple_qui_releve_reste_accepte():
    handler = ast.parse("try:\n    pass\nexcept (AssertionError, ValueError):\n    raise\n").body[0].handlers[0]

    assert write._avale_l_echec(handler) is False
