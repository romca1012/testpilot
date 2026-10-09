"""Lot VH-04, étape 5 (audit V7) — deux vérifications Odoo qui prouvaient trop peu.

- « l'action … est refusée » : seul un REFUS DE DROITS du serveur (`AccessError`/`AccessDenied`) prouve le refus. Avant, TOUTE
  exception comptait : une méthode mal orthographiée ou une panne RPC donnaient un vert.
- « un enregistrement … existe » : après un relevé du modèle, seuls les enregistrements APPARUS depuis comptent. Avant, un
  enregistrement déjà présent (même nom) faisait passer le test alors que l'action n'avait rien créé.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))
sys.path.insert(0, str(_STEPS_LIB / "odoo"))
import _odoo_droits_steps as droits  # noqa: E402
import _odoo_steps as steps  # noqa: E402


class _Notification:
    pass


class _Page:
    def locator(self, _sel):
        return _Notification()


class _Erreur(Exception):
    pass


class _Record:
    def __init__(self, exc):
        self._exc = exc

    def action_confirm(self):
        if self._exc:
            raise self._exc


def _ctx(exc):
    modele = types.SimpleNamespace(browse=lambda _id: _Record(exc))
    return types.SimpleNamespace(page=_Page(), odoo_version=(17, 0), last_record_model="sale.order", last_record_ids=[1],
                                 odoo=types.SimpleNamespace(env={"sale.order": modele}))


@pytest.fixture(autouse=True)
def _ecran_ok(monkeypatch):
    monkeypatch.setattr(droits, "constater_visible", lambda loc, message="": None)


# ── Refus d'action ────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("exc", [
    type("AccessError", (Exception,), {})("interdit"),
    _Erreur("odoo.exceptions.AccessError: Vous n'avez pas le droit"),
    type("RPCError", (Exception,), {"info": {"data": {"name": "odoo.exceptions.AccessDenied"}}})("refus"),
])
def test_un_refus_de_droits_du_serveur_prouve_le_refus(exc):
    droits.step_action_refusee(_ctx(exc), "action_confirm")


@pytest.mark.parametrize("exc", [
    AttributeError("'Record' object has no attribute 'action_confirmer'"),   # méthode mal orthographiée
    ConnectionError("RPC perdu"),                                            # panne
    _Erreur("odoo.exceptions.UserError: le devis est verrouillé"),           # refus métier, pas de droits
])
def test_falsifiable_une_autre_erreur_n_est_jamais_un_refus_prouve(exc):
    with pytest.raises(type(exc)):
        droits.step_action_refusee(_ctx(exc), "action_confirm")


# ── Existence cloisonnée ──────────────────────────────────────────────────────────────────────────────────


class _Modele:
    def __init__(self, enregistrements):
        self._e = enregistrements   # {id: nom}

    def search(self, domaine):
        ids = sorted(self._e)
        for champ, op, valeur in domaine:
            if champ == "id" and op == ">":
                ids = [i for i in ids if i > valeur]
            elif op == "=":
                ids = [i for i in ids if self._e[i] == valeur]
            elif op == "ilike":
                ids = [i for i in ids if valeur.lower() in self._e[i].lower()]
        return ids


def _ctx_existence(enregistrements, *, releve=None):
    ctx = types.SimpleNamespace(odoo=types.SimpleNamespace(env={"res.partner": _Modele(enregistrements)}))
    if releve is not None:
        setattr(ctx, steps._max_id_attr("res.partner"), releve)
    return ctx


@pytest.mark.parametrize("step, champ", [
    (steps.step_record_exists_field_value, "name"),
    (steps.step_record_exists_contains, '"name"'),
])
def test_falsifiable_un_enregistrement_anterieur_au_releve_ne_prouve_pas_la_creation(step, champ, monkeypatch):
    monkeypatch.setattr(steps, "constater", _constater_strict)
    ctx = _ctx_existence({7: "Dupont SARL"}, releve=10)   # « Dupont SARL » existait AVANT l'action

    with pytest.raises(AssertionError, match="apparus après le relevé"):
        step(ctx, champ, "Dupont SARL", "res.partner")


@pytest.mark.parametrize("step, champ", [
    (steps.step_record_exists_field_value, "name"),
    (steps.step_record_exists_contains, '"name"'),
])
def test_un_enregistrement_cree_apres_le_releve_est_trouve(step, champ, monkeypatch):
    monkeypatch.setattr(steps, "constater", _constater_strict)
    ctx = _ctx_existence({7: "Dupont SARL", 12: "Dupont SARL"}, releve=10)

    step(ctx, champ, "Dupont SARL", "res.partner")

    assert ctx.last_record_ids == [12]


def test_sans_releve_la_recherche_reste_globale(monkeypatch):
    monkeypatch.setattr(steps, "constater", _constater_strict)
    ctx = _ctx_existence({7: "Dupont SARL"})

    steps.step_record_exists_field_value(ctx, "name", "Dupont SARL", "res.partner")

    assert ctx.last_record_ids == [7]


def _constater_strict(condition, message=""):
    if not condition:
        raise AssertionError(message)
