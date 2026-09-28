"""Lot 08c (C6) — effets vérifiés côté serveur : état technique, champ numérique avec tolérance
devise, documents liés et leur état, rapport PDF.

⚠️ Les assertions RPC sont testées avec des fakes odoorpc (même patron que `_odoo_steps.py`
existant) — comportement RÉEL déjà mesuré pour ce type d'appel ailleurs dans le dépôt. Le seul
step qui touche l'UI (`step_rapport_pdf_genere`) est testé par délégation, non vérifié sur banc.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_effets_steps():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _odoo_effets_steps as steps
    return steps


class _FakeRecordSet:
    """odoorpc réel : `browse(un_id)` ou `browse([ids])` rendent tous les deux un recordset dont
    `.read(champs)` rend une LISTE de dicts (un par id, dans l'ordre) — jamais un objet par id."""

    def __init__(self, data_par_id, id_ou_ids):
        self._data_par_id = data_par_id
        self._ids = list(id_ou_ids) if isinstance(id_ou_ids, (list, tuple)) else [id_ou_ids]

    def read(self, champs):
        return [{c: self._data_par_id[i].get(c) for c in champs} for i in self._ids]


class _FakeModel:
    def __init__(self, data_par_id, fields=None):
        self._data_par_id = data_par_id
        self._fields = fields or {}

    def browse(self, id_ou_ids):
        return _FakeRecordSet(self._data_par_id, id_ou_ids)

    def fields_get(self, champs):
        return {c: {} for c in champs if c in self._fields}


class _FakeEnv:
    def __init__(self, modeles):
        self._modeles = modeles

    def __getitem__(self, modele):
        return self._modeles[modele]


def _ctx(modeles, *, last_record_model="sale.order", last_record_ids=(1,)):
    return types.SimpleNamespace(
        odoo=types.SimpleNamespace(env=_FakeEnv(modeles)),
        last_record_model=last_record_model, last_record_ids=list(last_record_ids))


# ── état technique ────────────────────────────────────────────────────────────

def test_etat_technique_compare_le_champ_state():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"state": "sale"}})}
    ctx = _ctx(modeles)

    steps.step_etat_technique(ctx, "sale")  # ne lève pas


def test_falsifiable_etat_technique_differe_echoue():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"state": "draft"}})}
    ctx = _ctx(modeles)

    with pytest.raises(AssertionError):
        steps.step_etat_technique(ctx, "sale")


def test_etat_technique_sans_enregistrement_en_contexte_leve_runtime_error():
    steps = _charger_effets_steps()
    ctx = types.SimpleNamespace()  # aucun last_record_ids

    with pytest.raises(RuntimeError):
        steps.step_etat_technique(ctx, "sale")


# ── champ numérique avec tolérance devise ──────────────────────────────────────

def test_champ_vaut_nombre_dans_la_tolerance_par_defaut():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"amount_total": 100.004}}, fields={})}
    ctx = _ctx(modeles)

    steps.step_champ_vaut_nombre(ctx, "amount_total", 100.0)  # 0.004 <= tolérance repli 0.01


def test_falsifiable_champ_hors_tolerance_echoue():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"amount_total": 105.0}}, fields={})}
    ctx = _ctx(modeles)

    with pytest.raises(AssertionError):
        steps.step_champ_vaut_nombre(ctx, "amount_total", 100.0)


def test_tolerance_devise_lit_res_currency_rounding_si_disponible():
    steps = _charger_effets_steps()
    modeles = {
        "sale.order": _FakeModel({1: {"currency_id": [7, "EUR"]}}, fields={"currency_id": {}}),
        "res.currency": _FakeModel({7: {"rounding": 0.1}}),
    }
    ctx = _ctx(modeles)

    assert steps._tolerance_devise(ctx, "sale.order", 1) == 0.05


def test_tolerance_devise_repli_si_pas_de_champ_currency_id():
    steps = _charger_effets_steps()
    modeles = {"stock.picking": _FakeModel({1: {}}, fields={})}
    ctx = _ctx(modeles, last_record_model="stock.picking")

    assert steps._tolerance_devise(ctx, "stock.picking", 1) == 0.01


# ── documents liés ──────────────────────────────────────────────────────────────

def test_n_lies_par_champ_pose_last_related():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"picking_ids": [10, 11]}})}
    ctx = _ctx(modeles)

    steps.step_a_n_lies_par_champ(ctx, 2, "stock.picking", "picking_ids")

    assert ctx.last_related_ids == [10, 11]
    assert ctx.last_related_model == "stock.picking"


def test_falsifiable_n_lies_diverge_echoue():
    steps = _charger_effets_steps()
    modeles = {"sale.order": _FakeModel({1: {"picking_ids": [10]}})}
    ctx = _ctx(modeles)

    with pytest.raises(AssertionError):
        steps.step_a_n_lies_par_champ(ctx, 2, "stock.picking", "picking_ids")


def test_document_lie_etat_verifie_tous_les_lies():
    steps = _charger_effets_steps()
    modeles = {"stock.picking": _FakeModel({10: {"state": "done"}, 11: {"state": "done"}})}
    ctx = _ctx(modeles)
    ctx.last_related_ids = [10, 11]
    ctx.last_related_model = "stock.picking"

    steps.step_document_lie_etat(ctx, "stock.picking", "done")  # ne lève pas


def test_falsifiable_document_lie_etat_un_seul_diverge_echoue():
    steps = _charger_effets_steps()
    modeles = {"stock.picking": _FakeModel({10: {"state": "done"}, 11: {"state": "draft"}})}
    ctx = _ctx(modeles)
    ctx.last_related_ids = [10, 11]

    with pytest.raises(AssertionError):
        steps.step_document_lie_etat(ctx, "stock.picking", "done")


def test_document_lie_etat_sans_lies_en_contexte_leve_runtime_error():
    steps = _charger_effets_steps()
    ctx = types.SimpleNamespace()

    with pytest.raises(RuntimeError):
        steps.step_document_lie_etat(ctx, "stock.picking", "done")


def test_facture_liee_comptabilisee_interroge_account_move_posted(monkeypatch):
    steps = _charger_effets_steps()
    appels = []
    monkeypatch.setattr(steps, "_lies_sont_a_l_etat",
                        lambda ctx, modele, valeur: (appels.append((modele, valeur)), (True, ["posted"]))[1])
    ctx = types.SimpleNamespace()

    steps.step_facture_liee_comptabilisee(ctx)  # ne lève pas

    assert appels == [("account.move", "posted")]


def test_falsifiable_facture_liee_non_comptabilisee_echoue(monkeypatch):
    steps = _charger_effets_steps()
    modeles = {"account.move": _FakeModel({20: {"state": "draft"}})}
    ctx = _ctx(modeles)
    ctx.last_related_ids = [20]

    with pytest.raises(AssertionError):
        steps.step_facture_liee_comptabilisee(ctx)


# ── rapport PDF ───────────────────────────────────────────────────────────────

def test_rapport_pdf_genere_delegue_au_telechargement_et_controle_la_signature(monkeypatch, tmp_path):
    steps = _charger_effets_steps()
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4\ncontenu")

    appels_telechargement = []
    monkeypatch.setattr(steps, "telecharger_via",
                        lambda ctx, libelle: appels_telechargement.append(libelle))
    monkeypatch.setattr(steps, "_dernier_telechargement",
                        lambda ctx: {"nom": "rapport.pdf", "chemin": str(pdf)})
    monkeypatch.setattr(steps, "_texte_du_fichier", lambda chemin: "Facture n°1234")

    class _FakeGetByRole:
        def click(self, timeout=None):
            raise TimeoutError("pas de menu Imprimer sur cette vue")

    class _FakePage:
        def get_by_role(self, role, name=None):
            return types.SimpleNamespace(first=_FakeGetByRole())

    ctx = types.SimpleNamespace(page=_FakePage())

    steps.step_rapport_pdf_genere(ctx, "Facture")  # ne lève pas malgré l'échec du menu Imprimer

    assert appels_telechargement == ["Facture"]


def test_falsifiable_rapport_sans_signature_pdf_echoue(monkeypatch, tmp_path):
    steps = _charger_effets_steps()
    faux_pdf = tmp_path / "pas_un_pdf.pdf"
    faux_pdf.write_bytes(b"<html>erreur</html>")

    monkeypatch.setattr(steps, "telecharger_via", lambda ctx, libelle: None)
    monkeypatch.setattr(steps, "_dernier_telechargement",
                        lambda ctx: {"nom": "pas_un_pdf.pdf", "chemin": str(faux_pdf)})

    class _FakePage:
        def get_by_role(self, role, name=None):
            raise Exception("pas de menu")

    ctx = types.SimpleNamespace(page=_FakePage())

    with pytest.raises(AssertionError):
        steps.step_rapport_pdf_genere(ctx, "Facture")
