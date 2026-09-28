"""Lot 08d — utilisateurs, sociétés, droits : refus d'accès (UI + RPC), société de travail.

`je me connecte en tant que "<libellé>"` (D8) est déjà partagé avec le lot 07b-1
(`_odoo_steps.py::step_connect_as`) — non testé ici, déjà couvert ailleurs.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_droits_steps():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _odoo_droits_steps as steps
    return steps


# ── l'action "<méthode>" est refusée ────────────────────────────────────────────

class _FakeNotification:
    def __init__(self, visible=True):
        self._visible = visible


class _FakePageRefus:
    def __init__(self, *, notif_visible=True):
        self.notif = _FakeNotification(notif_visible)

    def locator(self, sel):
        assert sel == ".o_notification_manager .o_notification.border-danger"
        return self.notif


class _FakeRecordRefusant:
    """Le browse().methode() lève — l'action est refusée côté serveur."""

    def action_confirm(self):
        raise Exception("AccessError: interdit pour ce groupe")


class _FakeRecordAutorisant:
    def action_confirm(self):
        return True  # l'appel RÉUSSIT — pas de refus réel côté serveur


class _FakeModelRPC:
    def __init__(self, record):
        self._record = record

    def browse(self, ids):
        return self._record


def test_action_refusee_ok_quand_notification_visible_et_rpc_refuse(monkeypatch):
    steps = _charger_droits_steps()
    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)  # visible : ne lève pas
    ctx = types.SimpleNamespace(
        page=_FakePageRefus(), odoo_version=(17, 0),
        last_record_model="sale.order", last_record_ids=[1],
        odoo=types.SimpleNamespace(env={"sale.order": _FakeModelRPC(_FakeRecordRefusant())}))

    steps.step_action_refusee(ctx, "action_confirm")  # ne lève pas


def test_falsifiable_action_refusee_echoue_si_notification_absente(monkeypatch):
    steps = _charger_droits_steps()

    def _leve(loc, message=""):
        raise AssertionError(message)
    monkeypatch.setattr(steps, "constater_visible", _leve)
    ctx = types.SimpleNamespace(
        page=_FakePageRefus(notif_visible=False), odoo_version=(17, 0),
        last_record_model="sale.order", last_record_ids=[1],
        odoo=types.SimpleNamespace(env={"sale.order": _FakeModelRPC(_FakeRecordRefusant())}))

    with pytest.raises(AssertionError):
        steps.step_action_refusee(ctx, "action_confirm")


def test_falsifiable_action_refusee_echoue_si_l_appel_rpc_reussit_vraiment(monkeypatch):
    """La preuve centrale du step : une notification visible ne suffit PAS si l'appel RPC direct
    de la méthode réussit quand même — c'est exactement le refus « en apparence seulement » que
    ce step doit détecter."""
    steps = _charger_droits_steps()
    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    ctx = types.SimpleNamespace(
        page=_FakePageRefus(notif_visible=True), odoo_version=(17, 0),
        last_record_model="sale.order", last_record_ids=[1],
        odoo=types.SimpleNamespace(env={"sale.order": _FakeModelRPC(_FakeRecordAutorisant())}))

    with pytest.raises(AssertionError):
        steps.step_action_refusee(ctx, "action_confirm")


def test_action_refusee_sans_enregistrement_en_contexte_leve_runtime_error(monkeypatch):
    steps = _charger_droits_steps()
    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    ctx = types.SimpleNamespace(page=_FakePageRefus(), odoo_version=(17, 0))  # pas de last_record_ids

    with pytest.raises(RuntimeError):
        steps.step_action_refusee(ctx, "action_confirm")


# ── je travaille dans la société ────────────────────────────────────────────────

class _FakeClickable:
    def __init__(self, journal, nom):
        self._journal = journal
        self._nom = nom

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._journal.append(self._nom)


class _FakePageSociete:
    def __init__(self, *, echoue_sur=None):
        self.clics = []
        self.url = "https://x.example.com/web"
        self._echoue_sur = echoue_sur or set()

    def locator(self, sel):
        return _FakeClickable(self.clics, sel)

    def get_by_text(self, texte, exact=False):
        if texte in self._echoue_sur:
            raise Exception(f"société '{texte}' introuvable")
        return _FakeClickable(self.clics, texte)


def test_travailler_dans_la_societe_ouvre_le_selecteur_puis_choisit_le_nom(monkeypatch):
    steps = _charger_droits_steps()
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda page: None)
    page = _FakePageSociete()
    ctx = types.SimpleNamespace(page=page)

    steps.step_travailler_dans_la_societe(ctx, "Filiale Nord")

    assert "Filiale Nord" in page.clics


def test_falsifiable_societe_absente_leve_element_introuvable(monkeypatch):
    steps = _charger_droits_steps()
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda page: None)
    page = _FakePageSociete(echoue_sur={"Société inexistante"})
    ctx = types.SimpleNamespace(page=page)

    with pytest.raises(steps.ElementIntrouvableError):
        steps.step_travailler_dans_la_societe(ctx, "Société inexistante")
