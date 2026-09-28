"""Lot 08b (C6) — steps de gestion ERP Odoo : formulaire par modèle technique, relation,
ligne x2many, enregistrer/annuler, bouton d'action, assistant, barre d'état, liste filtrée.

⚠️ Ces tests prouvent le MÉCANISME (délégation aux bons helpers, avec les bons arguments,
résolution RPC de l'action) — jamais le comportement Playwright réel contre un DOM Odoo (aucun
banc réel disponible dans ce cloud, voir `_selecteurs.py`). Suivent le même patron que
`test_odoo_steps_login_delegue.py` pour `navigate_menu`/`playwright_login`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_gestion_steps():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _odoo_gestion_steps as steps
    return steps


# ── Résolution RPC de l'action de fenêtre ──────────────────────────────────────

class _FakeModelRPC:
    def __init__(self, resultats):
        self._resultats = resultats
        self.appels = []

    def search(self, domaine, limit=None):
        self.appels.append((domaine, limit))
        return self._resultats

    def name_search(self, name, operator, limit=None):
        self.appels.append((name, operator, limit))
        return self._resultats_name_search.get(operator, [])


class _FakeOdooEnv:
    def __init__(self, modeles):
        self._modeles = modeles

    def __getitem__(self, modele):
        return self._modeles[modele]


def test_resoudre_action_fenetre_cherche_par_res_model():
    steps = _charger_gestion_steps()
    action_model = _FakeModelRPC([808])
    ctx = types.SimpleNamespace(odoo=types.SimpleNamespace(
        env=_FakeOdooEnv({"ir.actions.act_window": action_model})))

    action_id = steps._resoudre_action_fenetre(ctx, "it.equipment")

    assert action_id == 808
    assert action_model.appels == [([("res_model", "=", "it.equipment")], 1)]


def test_resoudre_action_fenetre_sans_action_leve_precondition():
    steps = _charger_gestion_steps()
    action_model = _FakeModelRPC([])
    ctx = types.SimpleNamespace(odoo=types.SimpleNamespace(
        env=_FakeOdooEnv({"ir.actions.act_window": action_model})))

    with pytest.raises(steps.PreconditionNonRemplieError):
        steps._resoudre_action_fenetre(ctx, "modele.inexistant")


# ── j'ouvre le formulaire de création du modèle ────────────────────────────────

class _FakePage:
    def __init__(self):
        self.urls = []
        self.url = "about:blank"

    def goto(self, url, **_k):
        self.urls.append(url)
        self.url = url


def test_ouvrir_creation_navigue_vers_l_url_de_l_action_et_pose_le_contexte(monkeypatch):
    steps = _charger_gestion_steps()
    action_model = _FakeModelRPC([808])
    page = _FakePage()
    ctx = types.SimpleNamespace(
        odoo=types.SimpleNamespace(env=_FakeOdooEnv({"ir.actions.act_window": action_model})),
        odoo_url="https://x.example.com", odoo_version=(17, 0), page=page)
    appels_attente = []
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: appels_attente.append(p))

    steps.step_ouvrir_creation(ctx, "it.equipment")

    assert page.urls == ["https://x.example.com/web#action=808&model=it.equipment&view_type=form"]
    assert appels_attente == [page]
    assert ctx.last_record_model == "it.equipment"
    assert ctx.last_record_ids == []


# ── j'ouvre l'enregistrement "<nom>" du modèle ─────────────────────────────────

def test_ouvrir_enregistrement_resout_l_id_par_name_search_exact_d_abord(monkeypatch):
    steps = _charger_gestion_steps()
    action_model = _FakeModelRPC([808])
    equip_model = _FakeModelRPC([])
    equip_model._resultats_name_search = {"=": [(42, "Ordinateur X")], "ilike": [(42, "Ordinateur X")]}
    page = _FakePage()
    ctx = types.SimpleNamespace(
        odoo=types.SimpleNamespace(env=_FakeOdooEnv({
            "ir.actions.act_window": action_model, "it.equipment": equip_model})),
        odoo_url="https://x.example.com", odoo_version=(18, 0), page=page)
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)

    steps.step_ouvrir_enregistrement(ctx, "Ordinateur X", "it.equipment")

    assert page.urls == ["https://x.example.com/odoo/action-808/42"]
    assert ctx.last_record_ids == [42]
    assert ctx.last_record_model == "it.equipment"


def test_ouvrir_enregistrement_absent_leve_precondition(monkeypatch):
    steps = _charger_gestion_steps()
    equip_model = _FakeModelRPC([])
    equip_model._resultats_name_search = {"=": [], "ilike": []}
    ctx = types.SimpleNamespace(
        odoo=types.SimpleNamespace(env=_FakeOdooEnv({"it.equipment": equip_model})),
        odoo_url="https://x.example.com", odoo_version=(18, 0), page=_FakePage())

    with pytest.raises(steps.PreconditionNonRemplieError):
        steps.step_ouvrir_enregistrement(ctx, "Introuvable", "it.equipment")


# ── je renseigne la relation ────────────────────────────────────────────────────

def test_renseigner_relation_delegue_a_select_field_value(monkeypatch):
    steps = _charger_gestion_steps()
    appels = []
    monkeypatch.setattr(steps, "select_field_value",
                        lambda page, value, field: appels.append((page, value, field)))
    ctx = types.SimpleNamespace(page="PAGE")

    steps.step_renseigner_relation(ctx, "agence_id", "AGENCE D'ABBEVILLE")

    assert appels == [("PAGE", "AGENCE D'ABBEVILLE", "agence_id")]


# ── j'ajoute une ligne à x2many ──────────────────────────────────────────────────

class _FakeRow:
    def __init__(self, valeurs):
        self._valeurs = valeurs

    def __getitem__(self, cle):
        return self._valeurs[cle]


class _FakeLocatorX2Many:
    def __init__(self, journal, nom=""):
        self._journal = journal
        self._nom = nom

    def locator(self, selecteur):
        return _FakeLocatorX2Many(self._journal, f"{self._nom}>{selecteur}")

    @property
    def first(self):
        return self


def test_ajouter_ligne_x2many_clique_ajouter_puis_remplit_la_ligne_selectionnee(monkeypatch):
    steps = _charger_gestion_steps()
    journal_clics = []
    journal_remplissage = []

    class _FakePageX2Many:
        def locator(self, selecteur):
            if selecteur == '.o_field_widget[name="order_line"]':
                return _FakeLocatorX2Many(journal_clics, "conteneur")
            if selecteur == ".o_selected_row":
                return _FakeLocatorX2Many(journal_clics, "ligne")
            raise AssertionError(f"sélecteur inattendu : {selecteur}")

    monkeypatch.setattr(steps, "click_first_actionable",
                        lambda page, candidats, quoi: journal_clics.append((candidats, quoi)))
    monkeypatch.setattr(steps, "fill_field",
                        lambda cible, champ, valeur: journal_remplissage.append((champ, valeur)))

    ctx = types.SimpleNamespace(page=_FakePageX2Many(), odoo_version=(17, 0),
                                table=[_FakeRow({"champ": "product_id", "valeur": "Souris"}),
                                      _FakeRow({"champ": "quantite", "valeur": "2"})])

    steps.step_ajouter_ligne_x2many(ctx, "order_line")

    assert journal_remplissage == [("product_id", "Souris"), ("quantite", "2")]


# ── enregistrer / annuler ────────────────────────────────────────────────────────

def test_enregistrer_document_clique_puis_capture_l_id_depuis_l_url(monkeypatch):
    steps = _charger_gestion_steps()
    page = types.SimpleNamespace(url="https://x.example.com/web#id=42&model=it.equipment")
    appels_clic = []
    monkeypatch.setattr(steps, "click_first_actionable",
                        lambda p, candidats, quoi: appels_clic.append((candidats, quoi)))
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)
    ctx = types.SimpleNamespace(page=page, odoo_version=(17, 0))

    steps.step_enregistrer_document(ctx)

    assert appels_clic and appels_clic[0][0] == [".o_form_button_save"]
    assert ctx.last_record_ids == [42]


def test_enregistrer_document_sans_id_dans_l_url_ne_pose_rien(monkeypatch):
    steps = _charger_gestion_steps()
    page = types.SimpleNamespace(url="https://x.example.com/web#action=808")
    monkeypatch.setattr(steps, "click_first_actionable", lambda p, c, quoi: None)
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)
    ctx = types.SimpleNamespace(page=page, odoo_version=(17, 0))

    steps.step_enregistrer_document(ctx)

    assert not hasattr(ctx, "last_record_ids")


def test_annuler_modifications_clique_le_bon_selecteur(monkeypatch):
    steps = _charger_gestion_steps()
    appels = []
    monkeypatch.setattr(steps, "click_first_actionable",
                        lambda p, candidats, quoi: appels.append(candidats))
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)
    ctx = types.SimpleNamespace(page=object(), odoo_version=(17, 0))

    steps.step_annuler_modifications(ctx)

    assert appels[0][0] == ".o_form_button_cancel"


# ── bouton d'action / assistant ────────────────────────────────────────────────

def test_bouton_action_resout_le_gabarit_et_passe_ident_pour_le_repli(monkeypatch):
    steps = _charger_gestion_steps()
    appels = []
    monkeypatch.setattr(steps, "click_first_actionable",
                        lambda p, candidats, quoi, ident=None: appels.append((candidats, ident)))
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)
    ctx = types.SimpleNamespace(page=object(), odoo_version=(17, 0))

    steps.step_bouton_action(ctx, "action_confirm")

    candidats, ident = appels[0]
    assert candidats == ['.o_form_view button[name="action_confirm"]']
    assert ident == "action_confirm"


def test_confirmer_dialogue_clique_le_bouton_principal(monkeypatch):
    steps = _charger_gestion_steps()
    appels = []
    monkeypatch.setattr(steps, "click_first_actionable",
                        lambda p, candidats, quoi: appels.append(candidats))
    monkeypatch.setattr(steps, "odoo_attendre_inactif", lambda p: None)
    ctx = types.SimpleNamespace(page=object(), odoo_version=(17, 0))

    steps.step_confirmer_dialogue(ctx)

    assert appels[0] == [".modal .modal-footer .btn-primary"]


# ── barre d'état / liste filtrée ────────────────────────────────────────────────

def test_etape_affichee_constate_le_texte_de_la_barre_de_statut(monkeypatch):
    steps = _charger_gestion_steps()
    appels = []
    monkeypatch.setattr(steps, "constater_texte",
                        lambda loc, attendu, message="": appels.append((loc, attendu)))

    class _P:
        def locator(self, sel):
            return f"LOC({sel})"

    ctx = types.SimpleNamespace(page=_P(), odoo_version=(17, 0))
    steps.step_etape_affichee(ctx, "Confirmé")

    assert appels == [('LOC(.o_statusbar_status [aria-checked="true"])', "Confirmé")]


def test_liste_n_enregistrements_constate_le_compte():
    steps = _charger_gestion_steps()
    appels = []

    class _Rows:
        def count(self):
            return 3

    class _P:
        def locator(self, sel):
            assert sel == ".o_data_row"
            return _Rows()

    orig = steps.constater
    def _espionne(condition, message=""):
        appels.append((condition, message))
        orig(condition, message)
    steps.constater = _espionne
    try:
        ctx = types.SimpleNamespace(page=_P())
        steps.step_liste_n_enregistrements(ctx, 3)
    finally:
        steps.constater = orig

    assert appels == [(True, "Liste : attendu 3 enregistrement(s), obtenu 3.")]


def test_falsifiable_liste_n_enregistrements_echoue_si_le_compte_diverge():
    steps = _charger_gestion_steps()

    class _Rows:
        def count(self):
            return 2

    class _P:
        def locator(self, sel):
            return _Rows()

    ctx = types.SimpleNamespace(page=_P())
    with pytest.raises(AssertionError):
        steps.step_liste_n_enregistrements(ctx, 3)
