"""Lot VH-04, étape 7 (D25) — le palier qui a résolu un clic est consigné : libellé exact, ou SOUS-CHAÎNE (`:has-text`).

Avant : seuls les champs (`locate_field`) et le repli adaptatif laissaient une trace ; un clic résolu par sous-chaîne (sans
casse, n'importe où dans le texte de l'élément) ne se distinguait pas d'un clic sur le libellé exact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


class _Cible:
    def __init__(self, ok):
        self.first = self
        self._ok = ok

    def click(self, timeout=None):
        if not self._ok:
            raise PlaywrightTimeout("absent")


class _Page:
    url = "http://app/x"

    def __init__(self, cliquables):
        self._cliquables = cliquables

    def locator(self, selecteur):
        return _Cible(selecteur in self._cliquables)


@pytest.fixture
def paliers(tmp_path, monkeypatch):
    chemin = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(H.SELECTOR_TIER_FILE_ENV, str(chemin))
    return lambda: [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]


def test_un_clic_par_sous_chaine_est_consigne_comme_tel(paliers):
    candidats = ["button[name='valider']", "button:has-text('Valider')"]

    H.click_first_actionable(_Page({"button:has-text('Valider')"}), candidats, quoi="Bouton 'Valider'", timeout=100)

    assert paliers()[-1]["tier"] == H.PALIER_CLIC_SOUS_CHAINE
    assert paliers()[-1]["ident"] == "clic:Bouton 'Valider'"


def test_falsifiable_un_clic_exact_n_est_pas_une_sous_chaine(paliers):
    candidats = ["button[name='valider']", "button:has-text('Valider')"]

    H.click_first_actionable(_Page({"button[name='valider']"}), candidats, quoi="Bouton 'Valider'", timeout=100)

    assert paliers()[-1]["tier"] == H.PALIER_CLIC
