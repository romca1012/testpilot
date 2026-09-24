"""Lot 03 (D3) — `constater*` : chaque appel, réussi OU échoué, consigne une ligne dans le sidecar.

Falsifiabilité : chaque helper lève `AssertionError` quand la condition n'est pas satisfaite, ET
consigne alors `ok: false` — jamais l'un sans l'autre.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))

import _base_helpers as H  # noqa: E402


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    chemin = tmp_path / "constats.jsonl"
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(chemin))
    H.definir_etat_constat(scenario="[Nominal] test", step_type="then")

    def lignes():
        if not chemin.exists():
            return []
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]

    return lignes


# ── constater ───────────────────────────────────────────────────────────────────────────────

def test_un_alors_qui_constate_deux_fois_ecrit_deux_lignes(sidecar):
    H.constater(1 == 1, "a")
    H.constater("x" in "xyz", "b")

    assert sidecar() == [{"scenario": "[Nominal] test", "step_type": "then", "ok": True}] * 2


def test_un_constat_echoue_leve_avec_son_message_et_ecrit_ok_false(sidecar):
    with pytest.raises(AssertionError, match="attendu 3, obtenu 2"):
        H.constater(2 == 3, "attendu 3, obtenu 2")

    assert [l["ok"] for l in sidecar()] == [False]


def test_le_type_de_step_courant_accompagne_le_constat(sidecar):
    H.definir_etat_constat(step_type="given")
    H.constater(True)

    assert sidecar()[0]["step_type"] == "given"


def test_hors_run_behave_aucune_variable_donc_rien_n_est_ecrit_et_rien_ne_casse(monkeypatch, tmp_path):
    monkeypatch.delenv(H.CONSTATS_FILE_ENV, raising=False)

    H.constater(True)
    with pytest.raises(AssertionError):
        H.constater(False, "x")


def test_un_sidecar_inecrivable_ne_fait_pas_echouer_le_test_mais_ne_prouve_rien(monkeypatch, tmp_path):
    """Le sens PRUDENT : l'échec d'écriture n'est pas un `conforme` — le constat n'est simplement pas
    compté, donc le verdict retombe en `indetermine`."""
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "dossier" / "inexistant" / "c.jsonl"))

    H.constater(True)  # pas d'exception


# ── constater_visible / constater_texte ─────────────────────────────────────────────────────

class _Expect:
    """Double de `playwright.sync_api.expect` : réussit ou lève, comme la vraie assertion web-first."""

    def __init__(self, ok, journal):
        self._ok, self._journal = ok, journal

    def __call__(self, locator):
        self._journal.append(("expect", locator))
        return self

    def to_be_visible(self, **options):
        self._journal.append(("visible", options))
        if not self._ok:
            raise AssertionError("Locator expected to be visible")

    def to_contain_text(self, attendu, **options):
        self._journal.append(("contient", attendu))
        if not self._ok:
            raise AssertionError(f"Locator expected to contain text {attendu!r}")

    def to_have_text(self, attendu, **options):
        self._journal.append(("egal", attendu))
        if not self._ok:
            raise AssertionError(f"Locator expected to have text {attendu!r}")


def test_constater_visible_reussi_consigne_ok_true(sidecar, monkeypatch):
    journal = []
    monkeypatch.setattr(H, "expect", _Expect(True, journal))

    H.constater_visible("loc", "message", timeout=1500)

    assert [l["ok"] for l in sidecar()] == [True]
    assert ("visible", {"timeout": 1500}) in journal


def test_constater_visible_echoue_sur_un_element_absent_et_consigne_ok_false(sidecar, monkeypatch):
    monkeypatch.setattr(H, "expect", _Expect(False, []))

    with pytest.raises(AssertionError, match="aucune erreur affichée"):
        H.constater_visible("loc", "aucune erreur affichée")

    assert [l["ok"] for l in sidecar()] == [False]


@pytest.mark.parametrize("exact, attendu_appel", [(False, "contient"), (True, "egal")])
def test_constater_texte_reussi_et_echoue(sidecar, monkeypatch, exact, attendu_appel):
    journal = []
    monkeypatch.setattr(H, "expect", _Expect(True, journal))
    H.constater_texte("loc", "Bonjour", exact=exact)
    assert (attendu_appel, "Bonjour") in journal

    monkeypatch.setattr(H, "expect", _Expect(False, []))
    with pytest.raises(AssertionError):
        H.constater_texte("loc", "Bonjour", exact=exact)

    assert [l["ok"] for l in sidecar()] == [True, False]


# ── constat (décorateur) ────────────────────────────────────────────────────────────────────

def test_le_decorateur_consigne_un_constat_par_appel_reussi_ou_echoue(sidecar):
    @H.constat
    def verifier(valeur):
        if valeur != 1:
            raise AssertionError("pas 1")
        return "ok"

    assert verifier(1) == "ok"
    with pytest.raises(AssertionError, match="pas 1"):
        verifier(2)

    assert [l["ok"] for l in sidecar()] == [True, False]


def test_le_decorateur_ne_consigne_rien_pour_une_autre_exception(sidecar):
    """Un prérequis manquant, une panne du test, un 5xx… ne sont PAS un constat sur l'application."""

    @H.constat
    def planter():
        raise H.PreconditionNonRemplieError("module absent")

    with pytest.raises(H.PreconditionNonRemplieError):
        planter()

    assert sidecar() == []


# ── Les helpers de la bibliothèque consignent bien ──────────────────────────────────────────

class _Locateur:
    def __init__(self, textes):
        self._textes = textes

    def count(self):
        return len(self._textes)

    def nth(self, i):
        import types
        return types.SimpleNamespace(inner_text=lambda: self._textes[i])


class _Page:
    def __init__(self, textes):
        self._textes = textes

    def locator(self, _selecteur):
        return _Locateur(self._textes)


def test_no_error_with_keywords_constate_meme_quand_aucune_erreur_n_est_affichee(sidecar):
    H.no_error_with_keywords(_Page([]), "interdit", "banni")

    assert [l["ok"] for l in sidecar()] == [True], "une absence affirmée est un constat exécuté"


def test_no_error_with_keywords_echoue_sur_un_message_fautif_et_le_consigne(sidecar):
    with pytest.raises(AssertionError, match="interdit"):
        H.no_error_with_keywords(_Page(["Mot interdit détecté"]), "interdit", "banni")

    assert [l["ok"] for l in sidecar()] == [False]


def test_no_duplicate_constate_dans_les_deux_sens(sidecar):
    class _Env(dict):
        pass

    env = _Env({"m": type("M", (), {"search": lambda self, dom: [1]})()})
    H.no_duplicate(env, "m", "f", "v")
    env2 = _Env({"m": type("M", (), {"search": lambda self, dom: [1, 2]})()})
    with pytest.raises(AssertionError, match="Doublon"):
        H.no_duplicate(env2, "m", "f", "v")

    assert [l["ok"] for l in sidecar()] == [True, False]
