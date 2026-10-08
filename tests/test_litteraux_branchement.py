"""Lot VH-05 (D24) — le contrôle des littéraux observés est BLOQUANT dans les outils d'écriture (plan verdict honnête).

Ce que ces tests prouvent : `write_feature_file` / `write_test_plan` refusent un champ, un bouton cité qui n'a jamais été observé
(cas réels de `base-3` : `username`), en donnant le nom observé ; `write_steps_file` refuse le réseau direct et un `context.X`
inventé (tous connecteurs), les sélecteurs par texte libre et les libellés non observés (connecteur web avec annuaire) ; ce que
l'agent vient d'inspecter compte comme observé ; et, sens inverse, les trois causes de refus à tort relevées par la revue
(titre de page, paramètre de Plan du scénario, `response.request`) n'en sont pas.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.generation import litteraux_observes as lo
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import inspect as outils_inspect
from testpilot.generation.tools import write as w

MODELE = {"pages": {
    "/connexion": {"champs": [{"name": "identifiant", "label": "Identifiant"},
                              {"name": "mot_de_passe", "label": "Mot de passe", "type": "password"}],
                   "actions": [{"label": "Se connecter"}], "liens": []},
    "/produits": {"champs": [{"name": "quantite", "label": "Quantité de Clavier mécanique"}],
                  "actions": [{"label": "Ajouter Clavier mécanique au panier"}], "liens": []},
}}
ATTRIBUTS = frozenset(lo.attributs_du_harnais(config.BEHAVE_RUNTIME_DIR))


def _ctx(tmp_path, annuaire=True, attributs=True):
    return ToolContext(module_name="m", generated_dir=tmp_path,
                       annuaire=lo.annuaire_depuis_modele(MODELE) if annuaire else None,
                       attributs_contexte=ATTRIBUTS if attributs else frozenset())


def _feature(*etapes):
    return "\n".join(["# language: fr", "Fonctionnalité: f", "  Scénario: s", *[f"    {e}" for e in etapes], ""])


# ── .feature ──────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_un_champ_jamais_observe_est_refuse_a_l_ecriture(tmp_path):
    sortie = w.write_feature_file(_ctx(tmp_path), _feature(
        "Soit j'accède à la page de connexion sans me connecter",
        'Quand je renseigne le champ "username" avec la valeur "testeur"',
        'Alors la page affiche le texte "Produits"'))

    assert not sortie.ok and "LITTERAL_NON_OBSERVE" in sortie.observation and "username" in sortie.observation
    assert not (tmp_path / "m.feature").exists()


def test_un_test_qui_cite_ce_qui_a_ete_observe_est_ecrit(tmp_path):
    sortie = w.write_feature_file(_ctx(tmp_path), _feature(
        "Soit j'accède à la page de connexion sans me connecter",
        'Quand je renseigne le champ "identifiant" avec la valeur "testeur"',
        'Et je clique sur le bouton "Se connecter"',
        'Alors la page affiche le texte "Produits"'))

    assert sortie.ok, sortie.observation


def test_une_page_absente_de_l_annuaire_n_est_qu_une_indication(tmp_path):
    """Une page dynamique (`/commande/<numéro>`) peut n'avoir jamais été explorée : jamais un refus."""
    sortie = w.write_feature_file(_ctx(tmp_path), _feature('Soit j\'ouvre la page "/commande/CMD-0001"',
                                                           'Alors la page affiche le texte "Commande"'))

    assert sortie.ok and "Attention" in sortie.observation


def test_un_parametre_de_plan_du_scenario_n_est_pas_refuse(tmp_path):
    contenu = "\n".join(["# language: fr", "Fonctionnalité: f", "  Plan du scénario: s",
                         "    Soit j'accède à la page de connexion sans me connecter",
                         '    Quand je renseigne le champ "<champ>" avec la valeur "x"',
                         '    Alors la page affiche le texte "Erreur"', "    Exemples:", "      | champ |",
                         "      | identifiant |", ""])

    assert w.write_feature_file(_ctx(tmp_path), contenu).ok


def test_sans_annuaire_le_controle_se_tait(tmp_path):
    sortie = w.write_feature_file(_ctx(tmp_path, annuaire=False), _feature(
        'Quand je renseigne le champ "username" avec la valeur "x"', 'Alors la page affiche le texte "y"'))

    assert sortie.ok


def test_ce_que_l_agent_vient_d_inspecter_compte_comme_observe(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.connector = SimpleNamespace(inspect_page_snapshot=lambda url: {
        "url": url, "error": "", "elements": [{"role": "button", "nom": "Valider la commande", "type": "submit"}]})

    outils_inspect.inspect_page_snapshot(ctx, "/panier")
    sortie = w.write_feature_file(ctx, _feature('Soit j\'ouvre la page "/produits"',
                                                'Quand je clique sur le bouton "Valider la commande"',
                                                'Alors la page affiche le texte "Merci"'))

    assert sortie.ok, sortie.observation


# ── _steps.py ─────────────────────────────────────────────────────────────────────────────────────────────

ENTETE = "from behave import given, when, then\nfrom _base_helpers import constater\n"


@pytest.mark.parametrize("corps, annuaire", [
    ("@when('x')\ndef s(context):\n    context.page.request.get('/__etat')\n", False),     # tous connecteurs
    ("@when('x')\ndef s(context):\n    u = context.base_url\n", False),                     # tous connecteurs
    ("@when('x')\ndef s(context):\n    context.page.locator(\"button:has-text('Ajouter')\").click()\n", True),
    ("@when('x')\ndef s(context, n):\n    context.page.get_by_label(f'Quantite de {n}').fill('2')\n", True),
])
def test_falsifiable_le_code_qui_cite_ce_qui_n_a_pas_ete_observe_est_refuse(corps, annuaire, tmp_path):
    sortie = w.write_steps_file(_ctx(tmp_path, annuaire=annuaire), ENTETE + corps)

    assert not sortie.ok and "LITTERAL_NON_OBSERVE" in sortie.observation


@pytest.mark.parametrize("corps", [
    # titre de page : l'annuaire ne relève pas les titres, ce n'est pas un élément interactif
    "@then('merci')\ndef s(context):\n    constater(context.page.get_by_role('heading', name='Merci').count() == 1, 't')\n",
    # observation réseau légitime (lot 4 : soumission prouvée)
    "@then('envoyé')\ndef s(context):\n    with context.page.expect_response('**/clients') as r:\n        pass\n"
    "    constater(r.value.request.method == 'POST', 'post')\n",
    # libellé observé, accent compris
    "@when('x')\ndef s(context, n):\n    context.page.get_by_label(f'Quantité de {n}').fill('2')\n",
])
def test_les_formes_legitimes_ne_sont_pas_refusees(corps, tmp_path):
    sortie = w.write_steps_file(_ctx(tmp_path), ENTETE + corps)

    assert sortie.ok, sortie.observation


def test_hors_connecteur_web_les_selecteurs_ne_sont_pas_juges(tmp_path):
    """Sans annuaire (connecteur Odoo aujourd'hui) : seuls réseau et contexte sont contrôlés."""
    corps = "@when('x')\ndef s(context):\n    context.page.locator(\"button:has-text('Valider')\").click()\n"

    assert w.write_steps_file(_ctx(tmp_path, annuaire=False), ENTETE + corps).ok


# ── L'agent construit l'annuaire du projet web, et seulement lui ──────────────────────────────────────────


@pytest.mark.parametrize("connecteur, attendu", [("web", True), ("odoo", False)])
def test_l_agent_branche_l_annuaire_pour_un_projet_web_seulement(connecteur, attendu, monkeypatch, tmp_path):
    from testpilot.analysis.plan import ScenarioIntent, TestPlan
    from testpilot.generation import agent as agent_mod

    vus = {}

    def capture(**kwargs):
        vus["ctx"] = kwargs["ctx"]

    monkeypatch.setattr(agent_mod.domain_model, "charger_modele", lambda projet: MODELE)
    monkeypatch.setattr(agent_mod, "run_loop", capture)
    monkeypatch.setattr(agent_mod.config, "GENERATED_DIR", tmp_path)
    plan = TestPlan(module_name="m", models=[], scenarios=[ScenarioIntent(name="s", type="nominal", action="a",
                                                                          persona="p", expected_outcome="e")],
                    personas=["p"], portal_routes=[], risks=[], raw_spec="")
    try:
        agent_mod.GenerationAgent(llm=SimpleNamespace(), connector=None, dry_runner=None).generate(
            plan, projet={"id": 1, "connector_type": connecteur})
    except Exception:
        pass  # la suite de `generate` après la boucle n'intéresse pas ce test

    assert (vus["ctx"].annuaire is not None) is attendu
    assert "page" in vus["ctx"].attributs_contexte
