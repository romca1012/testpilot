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
    def __init__(self, record, *, lisible=True):
        self._record = record
        self._lisible = lisible

    def search_count(self, domain):
        if self._lisible == "refus":
            raise Exception("AccessError: lecture interdite")
        return 1 if self._lisible else 0

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


def _ctx_compte_secondaire(record_du_principal):
    """Les écrans joués avec « lecteur » (step de connexion ou compte du cas, A70) ; `context.odoo` reste au principal (A73)."""
    return types.SimpleNamespace(
        page=_FakePageRefus(notif_visible=True), odoo_version=(17, 0),
        last_record_model="sale.order", last_record_ids=[1],
        odoo_url="http://odoo:8069", odoo_db="banc", odoo_user="lecteur", odoo_password="pw-lecteur",
        comptes={"principal": {"label": "principal", "user": "admin", "password": "pw-admin"},
                 "lecteur": {"label": "Lecteur", "user": "lecteur", "password": "pw-lecteur"}},
        odoo=types.SimpleNamespace(env={"sale.order": _FakeModelRPC(record_du_principal)}))


def test_falsifiable_a76_le_refus_se_prouve_avec_le_compte_qui_agit_pas_le_principal(monkeypatch):
    """A76 (revue de l'étape 4) : l'administrateur réussit l'appel, le lecteur est refusé. Le step doit tenter l'appel avec le
    LECTEUR — sinon une application saine sortirait « non conforme » (et l'action serait réellement exécutée par l'admin)."""
    steps = _charger_droits_steps()
    import _base_helpers

    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    ouvertes = []

    def _session(ctx, user, password):
        ouvertes.append((user, password))
        return types.SimpleNamespace(env={"sale.order": _FakeModelRPC(_FakeRecordRefusant())})
    monkeypatch.setattr(_base_helpers, "_ouvrir_session_rpc", _session)

    steps.step_action_refusee(_ctx_compte_secondaire(_FakeRecordAutorisant()), "action_confirm")   # ne lève pas
    assert ouvertes == [("lecteur", "pw-lecteur")]


def test_falsifiable_a76_le_compte_qui_agit_autorise_reste_un_echec(monkeypatch):
    """Le pendant : si le serveur laisse faire le lecteur, le refus n'était qu'à l'écran — non conforme, même si le principal,
    lui, aurait été refusé."""
    steps = _charger_droits_steps()
    import _base_helpers

    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    monkeypatch.setattr(_base_helpers, "_ouvrir_session_rpc",
                        lambda ctx, u, p: types.SimpleNamespace(env={"sale.order": _FakeModelRPC(_FakeRecordAutorisant())}))

    with pytest.raises(AssertionError):
        steps.step_action_refusee(_ctx_compte_secondaire(_FakeRecordRefusant()), "action_confirm")


@pytest.mark.parametrize("lisible", [False, "refus"])
def test_falsifiable_a76_un_enregistrement_invisible_pour_ce_compte_n_est_jamais_un_refus_prouve(monkeypatch, lisible):
    """Revue de l'étape 4 : le devis est créé par l'admin (A73), le lecteur ne voit que ses propres documents. L'appel lève un
    refus — mais de LECTURE. Sans ce garde-fou, le step concluait « action refusée » sans avoir jamais sollicité l'action."""
    steps = _charger_droits_steps()
    import _base_helpers

    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    monkeypatch.setattr(_base_helpers, "_ouvrir_session_rpc", lambda ctx, u, p: types.SimpleNamespace(
        env={"sale.order": _FakeModelRPC(_FakeRecordRefusant(), lisible=lisible)}))

    with pytest.raises(_base_helpers.ConstatNonConcluantError):
        steps.step_action_refusee(_ctx_compte_secondaire(_FakeRecordAutorisant()), "action_confirm")


def test_a76_le_compte_principal_garde_la_session_des_verifications(monkeypatch):
    steps = _charger_droits_steps()
    import _base_helpers

    monkeypatch.setattr(steps, "constater_visible", lambda loc, message="": None)
    monkeypatch.setattr(_base_helpers, "_ouvrir_session_rpc", lambda *a: pytest.fail("aucune session jetable pour le principal"))
    ctx = _ctx_compte_secondaire(_FakeRecordRefusant())
    ctx.odoo_user, ctx.odoo_password = "admin", "pw-admin"

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
