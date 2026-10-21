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
from behave import step_registry  # noqa: E402

# Importer les steps Odoo enregistre leurs libellés dans le registre GLOBAL de Behave dès la collecte : un fichier qui charge
# ensuite les steps web lèverait `AmbiguousStep` (mesuré : `test_connexion_execution.py`). Le registre est restauré aussitôt.
_REGISTRE_AVANT = {mot_cle: list(liste) for mot_cle, liste in step_registry.registry.steps.items()}
import _odoo_droits_steps as droits  # noqa: E402
import _odoo_steps as steps  # noqa: E402

for _mot_cle, _liste in _REGISTRE_AVANT.items():
    step_registry.registry.steps[_mot_cle][:] = _liste


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
    # A76 : le compte qui agit voit l'enregistrement (sinon le refus serait « non concluant », testé ailleurs).
    modele = types.SimpleNamespace(browse=lambda _id: _Record(exc), search_count=lambda domaine: 1)
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

    # Revue du lot (point 6) : non concluant — ni le vert d'avant (rien ne prouve la création), ni une accusation.
    with pytest.raises(steps.ConstatNonConcluantError, match="AVANT le relevé"):
        step(ctx, champ, "Dupont SARL", "res.partner")


@pytest.mark.parametrize("step, champ", [
    (steps.step_record_exists_field_value, "name"),
    (steps.step_record_exists_contains, '"name"'),
])
def test_falsifiable_un_enregistrement_absent_reste_un_constat_echoue(step, champ, monkeypatch):
    monkeypatch.setattr(steps, "constater", _constater_strict)
    ctx = _ctx_existence({7: "Autre"}, releve=10)

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


# ── Revue du lot (point 5) ────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_une_methode_privee_refusee_a_tous_ne_prouve_rien_sur_les_droits():
    exc = _Erreur("odoo.exceptions.AccessError: Private methods cannot be called remotely")

    with pytest.raises(RuntimeError, match="méthode privée"):
        droits.step_action_refusee(_ctx(exc), "_action_confirm")


def test_falsifiable_access_error_cite_au_milieu_du_message_n_est_pas_un_refus():
    """Le message peut contenir des données du test : seul l'en-tête écrit par le serveur compte."""
    exc = _Erreur("odoo.exceptions.UserError: le client « AccessError SARL » est bloqué")

    with pytest.raises(_Erreur):
        droits.step_action_refusee(_ctx(exc), "action_confirm")


# ── Revue du lot (point 6) : un enregistrement antérieur au relevé n'est ni un vert ni une accusation ─────────


def test_falsifiable_un_renommage_n_est_pas_une_accusation():
    """Relevé, puis renommage de « A » en « B » : l'id est antérieur au relevé. Avant la revue : `non_conforme` (faux rouge)."""
    from testpilot.verdict import defect_taxonomy as dt
    from testpilot.verdict import status as st

    ctx = _ctx_existence({7: "B"}, releve=10)

    with pytest.raises(steps.ConstatNonConcluantError, match="AVANT le relevé"):
        steps.step_record_exists_field_value(ctx, "name", "B", "res.partner")

    echec = types.SimpleNamespace(raw="_base_helpers.ConstatNonConcluantError: …", traceback_summary="",
                                  failure_type="error", step_type="then", scenario_name="s", step_text="")
    assert dt.classify_failure(echec) == dt.ALORS_SANS_CONSTAT
    verdict = st.scenario_verdict(types.SimpleNamespace(name="s", status="failed", error="", constats_echoues=0), [echec])
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
