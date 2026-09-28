"""Lot 06 (D6, F6) — le teardown générique Odoo : suppression par id EXACT enregistré, jamais par
domaine ni `max_id` ; cascade unlink → annulation → archivage → résidu ; ordre INVERSE de création ;
détection (jamais suppression) des résidus possibles au-dessus d'un `max_id` relevé.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config

_ENV_PATH = config.BEHAVE_RUNTIME_DIR / "environment.py"


def _load_environment():
    spec = importlib.util.spec_from_file_location("environment_teardown_test", _ENV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["environment_teardown_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_environment()


# ── Doublures Odoo minimales ─────────────────────────────────────────────────────────────────────

class _FakeRecordSet:
    def __init__(self, model, ids):
        self.model = model
        self.ids = list(ids)

    def unlink(self):
        if self.model.refuse_unlink:
            raise Exception("unlink refusé (document confirmé)")
        for i in self.ids:
            self.model.records.pop(i, None)
            self.model.unlinked.append(i)

    def action_cancel(self):
        if not self.model.a_action_cancel:
            raise Exception("action_cancel absent")
        self.model.annules.extend(self.ids)
        self.model.refuse_unlink = False  # l'annulation débloque le unlink suivant

    def button_cancel(self):
        if not self.model.a_button_cancel:
            raise Exception("button_cancel absent")
        self.model.annules.extend(self.ids)
        self.model.refuse_unlink = False

    def write(self, vals):
        if self.model.refuse_write:
            raise Exception("write refusé")
        for i in self.ids:
            if i in self.model.records:
                self.model.records[i].update(vals)
        self.model.archives.extend(self.ids)


class _FakeModel:
    def __init__(self, records=None, *, champ_actif=True, refuse_unlink=False,
                 a_action_cancel=False, a_button_cancel=False, refuse_write=False):
        self.records = dict(records or {})
        self.champ_actif = champ_actif
        self.refuse_unlink = refuse_unlink
        self.a_action_cancel = a_action_cancel
        self.a_button_cancel = a_button_cancel
        self.refuse_write = refuse_write
        self.unlinked: list[int] = []
        self.annules: list[int] = []
        self.archives: list[int] = []

    def browse(self, ids):
        return _FakeRecordSet(self, ids)

    def fields_get(self, names):
        return {"active": {}} if self.champ_actif and "active" in names else {}

    def search(self, domain, context=None):
        seuil = next(v for (champ, op, v) in [domain[0]] if champ == "id")
        return sorted(i for i in self.records if i > seuil)


class _FakeOdoo:
    def __init__(self, modeles: dict[str, _FakeModel]):
        self.env = modeles


def _contexte(mod, created_ordre, created=None):
    ctx = SimpleNamespace()
    ctx.created_ordre = list(created_ordre)
    ctx.created = created or {}
    for model, record_id in created_ordre:
        ctx.created.setdefault(model, [])
        if record_id not in ctx.created[model]:
            ctx.created[model].append(record_id)
    ctx._touched_models = {}
    ctx._residus = []
    return ctx


# ── register_created ─────────────────────────────────────────────────────────────────────────────

def test_register_created_est_idempotent(mod):
    ctx = SimpleNamespace(created={}, created_ordre=[])
    mod.register_created(ctx, "helpdesk.ticket", 42)
    mod.register_created(ctx, "helpdesk.ticket", 42)

    assert ctx.created == {"helpdesk.ticket": [42]}
    assert ctx.created_ordre == [("helpdesk.ticket", 42)]


def test_register_created_preserve_l_ordre_de_premiere_apparition(mod):
    ctx = SimpleNamespace(created={}, created_ordre=[])
    mod.register_created(ctx, "res.partner", 1)
    mod.register_created(ctx, "helpdesk.ticket", 42)
    mod.register_created(ctx, "res.partner", 2)

    assert ctx.created_ordre == [("res.partner", 1), ("helpdesk.ticket", 42), ("res.partner", 2)]


def test_register_created_tolere_l_absence_de_created_ordre(mod):
    """Un contexte de test minimal (comme `test_behave_harness.py`) sans `created_ordre` ne doit
    jamais lever — comportement historique de `context.created` seul préservé."""
    ctx = SimpleNamespace(created={})
    mod.register_created(ctx, "helpdesk.ticket", 42)
    assert ctx.created == {"helpdesk.ticket": [42]}


# ── _teardown_odoo_generique : cascade et ordre ─────────────────────────────────────────────────

def test_unlink_direct_reussit_sans_residu(mod):
    odoo = _FakeOdoo({"helpdesk.ticket": _FakeModel({1: {}})})
    ctx = _contexte(mod, [("helpdesk.ticket", 1)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert odoo.env["helpdesk.ticket"].unlinked == [1]
    assert ctx._residus == []


def test_falsifiable_annulation_puis_unlink_quand_le_document_est_confirme(mod):
    modele = _FakeModel({1: {}}, refuse_unlink=True, a_action_cancel=True)
    odoo = _FakeOdoo({"sale.order": modele})
    ctx = _contexte(mod, [("sale.order", 1)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert modele.annules == [1]
    assert modele.unlinked == [1]
    assert ctx._residus == []


def test_button_cancel_essaye_si_action_cancel_absent(mod):
    modele = _FakeModel({1: {}}, refuse_unlink=True, a_button_cancel=True)
    odoo = _FakeOdoo({"sale.order": modele})
    ctx = _contexte(mod, [("sale.order", 1)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert modele.annules == [1] and modele.unlinked == [1]


def test_falsifiable_archivage_si_ni_unlink_ni_annulation_ne_marchent(mod):
    modele = _FakeModel({1: {}}, refuse_unlink=True, champ_actif=True)
    odoo = _FakeOdoo({"res.partner": modele})
    ctx = _contexte(mod, [("res.partner", 1)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert modele.archives == [1]
    assert modele.unlinked == []
    assert ctx._residus == []


def test_falsifiable_residu_consigne_si_rien_ne_marche(mod):
    modele = _FakeModel({1: {}}, refuse_unlink=True, champ_actif=False)
    odoo = _FakeOdoo({"res.partner": modele})
    ctx = _contexte(mod, [("res.partner", 1)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert modele.unlinked == [] and modele.archives == []
    assert len(ctx._residus) == 1
    assert "res.partner id=1" in ctx._residus[0]


def test_ordre_inverse_de_creation_tous_modeles_confondus(mod):
    """Deux modèles créés A puis B : le teardown supprime B d'ABORD (ordre inverse), pas A."""
    ordre_suppression = []

    class _ModeleTraceur(_FakeModel):
        def browse(self, ids):
            ordre_suppression.append((self._nom, ids[0]))
            return super().browse(ids)

    m_a, m_b = _ModeleTraceur({1: {}}), _ModeleTraceur({2: {}})
    m_a._nom, m_b._nom = "res.partner", "helpdesk.ticket"
    odoo = _FakeOdoo({"res.partner": m_a, "helpdesk.ticket": m_b})
    ctx = _contexte(mod, [("res.partner", 1), ("helpdesk.ticket", 2)])

    mod._teardown_odoo_generique(ctx, odoo)

    assert ordre_suppression[0] == ("helpdesk.ticket", 2)
    assert ordre_suppression[1] == ("res.partner", 1)


def test_teardown_ne_touche_jamais_un_id_non_enregistre(mod):
    """Un id présent en base mais JAMAIS enregistré par `register_created` n'est jamais supprimé —
    seul `created_ordre` pilote le teardown (F6 : jamais par domaine)."""
    modele = _FakeModel({1: {}, 2: {}})
    odoo = _FakeOdoo({"res.partner": modele})
    ctx = _contexte(mod, [("res.partner", 1)])  # id 2 existe mais n'est PAS enregistré

    mod._teardown_odoo_generique(ctx, odoo)

    assert modele.unlinked == [1]
    assert 2 in modele.records  # jamais touché


# ── _signaler_residus_possibles : détection SEULE, jamais de suppression ───────────────────────

def test_falsifiable_un_surplus_non_enregistre_est_signale_jamais_supprime(mod):
    modele = _FakeModel({1: {}, 2: {}, 3: {}})
    odoo = _FakeOdoo({"res.partner": modele})
    ctx = _contexte(mod, [("res.partner", 1)])
    ctx._touched_models = {"res.partner": 1}  # baseline relevée à 1 ; 2 et 3 sont au-dessus

    mod._teardown_odoo_generique(ctx, odoo)  # supprime l'id 1, enregistré
    mod._signaler_residus_possibles(ctx, odoo)

    assert modele.unlinked == [1]
    assert 2 in modele.records and 3 in modele.records  # jamais supprimés
    assert any("2" in r and "3" in r for r in ctx._residus) or len(ctx._residus) == 1
    assert "résidu possible" in ctx._residus[-1]


def test_aucun_surplus_ne_produit_aucun_residu(mod):
    modele = _FakeModel({1: {}})
    odoo = _FakeOdoo({"res.partner": modele})
    ctx = _contexte(mod, [("res.partner", 1)])
    ctx._touched_models = {"res.partner": 1}

    mod._teardown_odoo_generique(ctx, odoo)
    mod._signaler_residus_possibles(ctx, odoo)

    assert ctx._residus == []


# ── _modele_depuis_route_formulaire / _enregistrer_creation_formulaire ─────────────────────────

@pytest.mark.parametrize("url,attendu", [
    ("https://x.example/website/form/helpdesk.ticket", "helpdesk.ticket"),
    ("https://x.example/website/form/res.partner?csrf=1", "res.partner"),
    ("https://x.example/website/form/helpdesk.ticket/", "helpdesk.ticket"),
])
def test_modele_depuis_route_formulaire_cas_valides(mod, url, attendu):
    assert mod._modele_depuis_route_formulaire(url) == attendu


@pytest.mark.parametrize("url", [
    "https://x.example/website/form/",
    "https://x.example/website/form/PasUnModele",
    "https://x.example/autre/chemin",
    "https://x.example/website/form/123",
])
def test_falsifiable_modele_depuis_route_formulaire_cas_invalides(mod, url):
    assert mod._modele_depuis_route_formulaire(url) == ""


def test_enregistrer_creation_formulaire_avec_modele_sur(mod):
    ctx = SimpleNamespace(created={}, created_ordre=[], _residus=[])
    mod._enregistrer_creation_formulaire(
        ctx, "https://x.example/website/form/helpdesk.ticket", {"id": 42})

    assert ctx.created == {"helpdesk.ticket": [42]}
    assert ctx._residus == []


def test_falsifiable_enregistrer_creation_formulaire_sans_modele_sur_consigne_un_residu(mod):
    ctx = SimpleNamespace(created={}, created_ordre=[], _residus=[])
    mod._enregistrer_creation_formulaire(ctx, "https://x.example/website/form/", {"id": 42})

    assert ctx.created == {}
    assert len(ctx._residus) == 1 and "42" in ctx._residus[0]


@pytest.mark.parametrize("corps", [
    {"error": "refusé"},
    {"error_fields": ["x"]},
    {"pas_un_id": True},
    "pas un dict",
    None,
])
def test_falsifiable_enregistrer_creation_formulaire_ignore_un_refus_ou_corps_invalide(mod, corps):
    ctx = SimpleNamespace(created={}, created_ordre=[], _residus=[])
    mod._enregistrer_creation_formulaire(ctx, "https://x.example/website/form/helpdesk.ticket", corps)

    assert ctx.created == {} and ctx._residus == []


# ── _instrumenter_creations_rpc : transparence + enregistrement automatique ────────────────────

def test_instrumenter_creations_rpc_enregistre_un_create_reussi(mod):
    appels = []

    def _reel(model, method, args=None, kwargs=None):
        appels.append((model, method, args, kwargs))
        if method == "create":
            return 42
        if method == "search":
            return []
        raise AssertionError("méthode inattendue")

    odoo = SimpleNamespace(execute_kw=_reel)
    ctx = SimpleNamespace(odoo=odoo, created={}, created_ordre=[], _touched_models={}, _residus=[])

    mod._instrumenter_creations_rpc(ctx)
    resultat = ctx.odoo.execute_kw("helpdesk.ticket", "create", [{"name": "x"}], {})

    assert resultat == 42  # valeur de retour INCHANGÉE
    assert ctx.created == {"helpdesk.ticket": [42]}


def test_falsifiable_instrumenter_creations_rpc_ne_modifie_ni_ne_masque_une_exception(mod):
    def _reel(model, method, args=None, kwargs=None):
        raise ValueError("boom")

    odoo = SimpleNamespace(execute_kw=_reel)
    ctx = SimpleNamespace(odoo=odoo, created={}, created_ordre=[], _touched_models={}, _residus=[])
    mod._instrumenter_creations_rpc(ctx)

    with pytest.raises(ValueError, match="boom"):
        ctx.odoo.execute_kw("helpdesk.ticket", "create", [{}], {})
    assert ctx.created == {}  # rien n'a été enregistré : l'appel a échoué


def test_instrumenter_creations_rpc_n_enregistre_rien_pour_une_lecture(mod):
    def _reel(model, method, args=None, kwargs=None):
        return [1, 2, 3] if method == "search" else None

    odoo = SimpleNamespace(execute_kw=_reel)
    ctx = SimpleNamespace(odoo=odoo, created={}, created_ordre=[], _touched_models={}, _residus=[])
    mod._instrumenter_creations_rpc(ctx)

    ctx.odoo.execute_kw("helpdesk.ticket", "search", [[]], {})

    assert ctx.created == {}


def test_instrumenter_creations_rpc_gere_un_create_par_lot(mod):
    def _reel(model, method, args=None, kwargs=None):
        return [10, 11] if method == "create" else []

    odoo = SimpleNamespace(execute_kw=_reel)
    ctx = SimpleNamespace(odoo=odoo, created={}, created_ordre=[], _touched_models={}, _residus=[])
    mod._instrumenter_creations_rpc(ctx)

    ctx.odoo.execute_kw("res.partner", "create", [[{}, {}]], {})

    assert ctx.created == {"res.partner": [10, 11]}


def test_instrumenter_creations_rpc_releve_la_baseline_une_seule_fois_par_modele(mod):
    appels_search = []

    def _reel(model, method, args=None, kwargs=None):
        if method == "search":
            appels_search.append(model)
            return [7]
        return 1 if method == "create" else None

    odoo = SimpleNamespace(execute_kw=_reel)
    ctx = SimpleNamespace(odoo=odoo, created={}, created_ordre=[], _touched_models={}, _residus=[])
    mod._instrumenter_creations_rpc(ctx)

    ctx.odoo.execute_kw("res.partner", "create", [{}], {})
    ctx.odoo.execute_kw("res.partner", "write", [[1], {}], {})

    assert appels_search == ["res.partner"]  # relevé UNE SEULE fois, pas à chaque appel
    assert ctx._touched_models == {"res.partner": 7}
