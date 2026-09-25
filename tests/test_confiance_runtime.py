"""Lot 05 (D5) — côté RUNTIME : le palier adaptatif porte son scénario, et le mode strict coupe le repli LLM.

Le verdict (`verdict/status.py`) lit ces sidecars pour qualifier un vert obtenu par repli ; ces tests fixent ce
que le sous-processus Behave écrit et ce qu'il refuse de faire.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import _adaptive_resolution  # noqa: E402
import _base_helpers as H  # noqa: E402
from testpilot.execution import behave_result  # noqa: E402


def test_les_noms_du_mode_strict_et_du_palier_sont_les_memes_des_deux_cotes():
    """Le sous-processus n'importe pas `testpilot` : les constantes sont dupliquées, ce test les tient d'accord."""
    assert H.MODE_STRICT_ENV == behave_result.MODE_STRICT_ENV == "TP_MODE_STRICT"
    assert H.PALIER_ADAPTATIF == behave_result.PALIER_ADAPTATIF


def test_une_resolution_adaptative_reussie_consigne_le_palier_ET_le_scenario(monkeypatch, tmp_path):
    sidecar = tmp_path / "selector_tiers.jsonl"
    monkeypatch.setenv(H.SELECTOR_TIER_FILE_ENV, str(sidecar))
    monkeypatch.delenv("TESTPILOT_QUALIFICATION", raising=False)
    monkeypatch.delenv(H.MODE_STRICT_ENV, raising=False)
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", lambda *a, **k: object())
    monkeypatch.setitem(H._ETAT_CONSTAT, "scenario", "Créer un ticket")

    resolu = H._repli_adaptatif(types.SimpleNamespace(), "champ_renomme", "saisir le sujet")

    assert resolu is not None
    ligne = json.loads(sidecar.read_text(encoding="utf-8").splitlines()[-1])
    assert ligne == {"ident": "champ_renomme", "tier": "adaptive", "scenario": "Créer un ticket"}


def test_un_palier_deterministe_consigne_aussi_son_scenario(monkeypatch, tmp_path):
    sidecar = tmp_path / "selector_tiers.jsonl"
    monkeypatch.setenv(H.SELECTOR_TIER_FILE_ENV, str(sidecar))
    monkeypatch.setitem(H._ETAT_CONSTAT, "scenario", "S2")

    H._record_selector_tier("champ", "name")

    assert json.loads(sidecar.read_text(encoding="utf-8"))["scenario"] == "S2"


def test_le_mode_strict_ne_fait_aucun_appel_adaptatif(monkeypatch):
    monkeypatch.delenv("TESTPILOT_QUALIFICATION", raising=False)
    monkeypatch.setenv(H.MODE_STRICT_ENV, "1")

    def interdit(*args, **kwargs):
        raise AssertionError("aucun appel LLM en mode strict")

    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", interdit)

    assert H._repli_adaptatif(types.SimpleNamespace(), "champ", "saisir") is None


def _page_menu_introuvable():
    """Une page où le libellé cherché n'existe pas : la cascade déterministe échoue."""
    class _Introuvable:
        first = property(lambda self: self)

        def click(self, timeout=None):
            raise PlaywrightTimeout("libellé introuvable")

    return types.SimpleNamespace(url="http://x/web", goto=lambda *a, **k: None,
                                 get_by_text=lambda t, exact=True: _Introuvable())


def test_falsifiable_un_menu_introuvable_appelle_le_llm_hors_strict_mais_jamais_en_strict(monkeypatch):
    """Sans le mode strict le repli est tenté (le test le prouve) ; avec, la cascade échoue et rien n'est appelé."""
    monkeypatch.delenv("TESTPILOT_QUALIFICATION", raising=False)
    monkeypatch.setattr(H, "_ouvrir_grille_applications", lambda page: None)
    appels = []

    def espion(*args, **kwargs):
        appels.append(args)
        return None  # le modèle « ne trouve rien » : l'échec d'origine remonte

    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", espion)
    contexte = types.SimpleNamespace(page=_page_menu_introuvable(), odoo_url="http://x")

    monkeypatch.delenv(H.MODE_STRICT_ENV, raising=False)
    with pytest.raises(PlaywrightTimeout):
        H.navigate_menu(contexte, "Ventes")
    assert appels, "précondition : hors strict, le repli adaptatif est bien tenté"

    appels.clear()
    monkeypatch.setenv(H.MODE_STRICT_ENV, "1")
    with pytest.raises(PlaywrightTimeout):
        H.navigate_menu(contexte, "Ventes")
    assert appels == [], "en mode strict, l'échec de la cascade n'appelle jamais le LLM"
