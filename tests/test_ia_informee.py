"""Étape 5 du plan unique (AV-1, AV-2, AV-5), interrupteur `TESTPILOT_IA_INFORMEE` (éteint) — l'IA reçoit le vrai type
d'application, la langue de l'interface et les pages que le cas vise, telles que l'exploration les a relevées.

Éteint : le message est celui d'avant, OCTET POUR OCTET (règle des interrupteurs : rien ne change sans mesure)."""

from __future__ import annotations

import pytest

from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.generation import agent as agent_mod
from testpilot.generation import interrupteurs, pages_observees
from testpilot.generation import prompt as prompt_mod

MODELE = {"connector_type": "web", "mesure_le": "2026-10-22", "pages": {
    "/clients/nouveau": {"titre": "Nouveau client", "champs": [
        {"name": "nom", "label": "Nom du client", "type": "text", "required": True, "visible": True,
         "contraintes": {"maxlength": 40}},
        {"name": "ville", "label": "Ville", "type": "text", "required": False, "visible": True},
        {"name": "pays", "label": "Pays", "tag": "select", "visible": True, "options": [["fr", "France"], ["be", "Belgique"]]},
        {"name": "jeton", "type": "hidden", "required": True, "visible": False}],
        "actions": [{"label": "Enregistrer", "soumet": True, "visible": True}],
        "liens": [{"href": "/clients", "text": "Retour à la liste"}, {"href": "https://ailleurs.example", "text": "Aide"}]},
    "/produits": {"titre": "Produits", "champs": [], "actions": [{"label": "Filtrer", "visible": True}], "liens": []},
}}


def _plan(routes=()):
    return TestPlan(module_name="m", models=[], personas=["u"], portal_routes=list(routes), risks=[], raw_spec="",
                    scenarios=[ScenarioIntent(name="Créer un client", type="nominal", action="saisir le nom",
                                              persona="u", expected_outcome="le client est créé")])


METIER = {"title": "Créer un client", "steps": ["Ouvrir la fiche Nouveau client", "Saisir le nom", "Enregistrer"],
          "expected_result": "Le client apparaît dans la liste"}


def test_eteint_le_message_est_celui_d_avant_octet_pour_octet(monkeypatch):
    monkeypatch.delenv(interrupteurs.ENV_IA_INFORMEE, raising=False)
    assert agent_mod._informee(_plan(), {"connector_type": "web", "browser_locale": "fr-FR"}, METIER) == {}
    assert prompt_mod.build_initial_message(_plan(), MODELE, METIER) == prompt_mod.build_initial_message(
        _plan(), MODELE, METIER, informee={})


def test_allume_le_type_la_langue_et_les_pages_visees(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    informee = agent_mod._informee(_plan(), {"connector_type": "web", "browser_locale": ""}, METIER)
    assert informee["connector_type"] == "web" and informee["langue"] == "fr-FR"
    message = prompt_mod.build_initial_message(_plan(), MODELE, METIER, informee=informee)
    assert "Type de système : web" in message and "Type de système : odoo" not in message
    assert "Langue de l'interface : fr-FR" in message
    assert "### /clients/nouveau — « Nouveau client »" in message
    assert "`nom` « Nom du client » (text, obligatoire)" in message and "40 caractères maximum" in message
    assert "`ville` « Ville » (text)" in message
    assert "choix : « fr », « be »" in message, "les options sont des paires [valeur, libellé]"
    assert "jeton" not in message, "un champ caché ne se remplit pas par l'interface"
    assert "« Enregistrer » (envoie le formulaire)" in message
    assert "« Retour à la liste » → /clients" in message and "ailleurs.example" not in message
    assert "/produits" not in message.split("## Pages observées")[1], "page sans rapport avec le cas"


def test_les_routes_du_plan_priment_sur_le_texte_du_cas():
    assert pages_observees.pages_visees(MODELE, ["/produits"], "Créer un client") == ["/produits"]
    assert pages_observees.pages_visees(MODELE, [], "Créer un client nouveau") == ["/clients/nouveau"]
    assert pages_observees.pages_visees(MODELE, [], "") == []


def test_sans_cartographie_ni_page_reconnue_rien_n_est_invente():
    assert pages_observees.section(None, [], "Créer un client") == ""
    assert pages_observees.section(MODELE, [], "texte sans rapport") == ""


def test_plafonds_le_message_ne_grossit_pas_avec_l_exploration():
    grosse = {"pages": {f"/client/{i}": {"titre": "client", "champs": [
        {"name": f"champ_{j}", "label": f"Libellé {j}", "type": "text", "visible": True} for j in range(80)],
        "actions": [{"label": f"Bouton {j}", "visible": True} for j in range(50)], "liens": []} for i in range(20)}}
    texte = pages_observees.section(grosse, [], "client")
    assert texte.count("### ") <= pages_observees.MAX_PAGES
    assert len(texte) <= pages_observees.MAX_CARACTERES + 40
    assert "champ_30" not in texte


@pytest.mark.parametrize("allume, attendu", [(False, {}), (True, {"connector_type": "web"})])
def test_l_analyse_de_la_specification_recoit_le_type_du_projet(monkeypatch, allume, attendu):
    from testpilot.api.services import generation_service

    if allume:
        monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    else:
        monkeypatch.delenv(interrupteurs.ENV_IA_INFORMEE, raising=False)
    assert generation_service._type_pour_l_analyse(None, project={"connector_type": "web"}) == attendu


def test_la_langue_n_est_annoncee_que_pour_une_application_web(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    assert agent_mod._informee(_plan(), {"connector_type": "odoo", "browser_locale": "fr-FR"}, METIER)["langue"] == ""
    assert agent_mod._informee(_plan(), {"connector_type": "web", "browser_locale": "en-US"}, METIER)["langue"] == "en-US"
    assert agent_mod._informee(_plan(), {"connector_type": "web", "browser_locale": "n'importe quoi"}, METIER)["langue"] == ""
    message = prompt_mod.build_initial_message(_plan(), MODELE, METIER, informee={"connector_type": "odoo", "langue": ""})
    assert "Langue de l'interface" not in message
