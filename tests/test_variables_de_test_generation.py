"""Lot PT-02d — la génération et les données de test (interrupteur `TESTPILOT_VARIABLES_DE_TEST`, allumé par défaut depuis A46 : ces tests l'éteignent par un `0`).

Ce que ces tests gardent :
1. interrupteur éteint : l'agent ne reçoit rien de plus, et ce qu'il peut écrire est contrôlé comme avant ;
2. allumé : l'agent reçoit les NOMS des variables, jamais leurs valeurs ;
3. à l'écriture, une variable inconnue, mal écrite, mal placée ou hors guillemets est refusée (règles de l'exécution) ;
   une valeur `{{nom}}` n'est pas confrontée aux enregistrements existants (elle change selon le jeu) ;
4. l'essai dans le bac à sable joue les valeurs du jeu « Par défaut » — jamais `{{client}}` saisi tel quel.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot import config
from testpilot.execution.behave_result import BehaveResult
from testpilot.generation import interrupteurs, prompt
from testpilot.generation import variables_de_test as vdt
from testpilot.generation.litteraux_observes import Annuaire
from testpilot.generation.references import verifier_references
from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools import essai as e
from testpilot.generation.tools.write import write_feature_file
from testpilot.guardrails import bac_a_sable
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo, TestDataRepo

PROJET = {"id": 1, "variables_de_test": [{"nom": "client", "description": "le client de la commande"},
                                         {"nom": "ville", "description": ""}],
          "valeurs_de_test_par_defaut": {"client": "Martin SARL", "ville": "Lyon"}}
FEATURE = """# language: fr
Fonctionnalité: Commande
  Scénario: Passer une commande
    Quand je renseigne le champ "Client" avec la valeur "{{client}}"
    Alors la page affiche le texte "Commande enregistrée"
"""


@pytest.fixture
def allume(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")


@pytest.fixture(autouse=True)
def eteint_sauf_mention_contraire(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "0")


def _plan():
    from testpilot.analysis.plan import TestPlan

    return TestPlan(module_name="commande", models=[], scenarios=[], personas=["client"], portal_routes=[], risks=[])


# ── 1-2. Ce que l'agent reçoit ────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_interrupteur_eteint_l_agent_ne_recoit_rien_de_plus():
    variables, valeurs = vdt.pour_l_agent(PROJET)

    assert (variables, valeurs) == ([], {})
    assert prompt.build_initial_message(_plan(), variables=variables) == prompt.build_initial_message(_plan())


def test_falsifiable_allume_l_agent_recoit_les_noms_jamais_les_valeurs(allume):
    variables, valeurs = vdt.pour_l_agent(PROJET)

    message = prompt.build_initial_message(_plan(), variables=variables)

    assert "{{client}}" in message and "le client de la commande" in message and "{{ville}}" in message
    assert "Martin SARL" not in message and "Lyon" not in message, "jamais une valeur dans le message"
    assert valeurs == {"client": "Martin SARL", "ville": "Lyon"}


def test_un_projet_sans_variable_ne_change_rien_meme_allume(allume):
    variables, _ = vdt.pour_l_agent({"id": 1, "variables_de_test": []})

    assert prompt.build_initial_message(_plan(), variables=variables) == prompt.build_initial_message(_plan())


def test_le_projet_porte_les_noms_et_les_valeurs_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "db.sqlite")
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    depot = TestDataRepo(conn)
    client = depot.creer_variable(pid, nom="client", description="le client")
    depot.creer_variable(pid, nom="ville")
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {client: "Martin SARL"})
    autre = depot.creer_jeu(pid, nom="Export")
    depot.poser_valeurs(pid, autre, {client: "Durand"})

    projet = ProjectRepo(conn).get(pid)

    assert projet["variables_de_test"] == [{"nom": "client", "description": "le client"}, {"nom": "ville", "description": ""}]
    assert projet["valeurs_de_test_par_defaut"] == {"client": "Martin SARL"}, "le jeu « Par défaut » seulement"
    conn.close()


# ── 3. À l'écriture ───────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ligne, faute", [
    ('Quand je renseigne le champ "Client" avec la valeur "{{pays}}"', "variable inconnue « pays »"),
    ('Quand je renseigne le champ "Client" avec la valeur "{{client}"', "mal écrite ou mal placée"),
    ("Quand je renseigne le champ \"Quantité\" avec {{client}} articles", "entre guillemets"),
])
def test_falsifiable_une_variable_fautive_est_refusee(ligne, faute):
    feature = FEATURE.replace('Quand je renseigne le champ "Client" avec la valeur "{{client}}"', ligne)

    assert any(faute in f for f in vdt.refus(feature, frozenset({"client", "ville"})))


def test_une_variable_bien_ecrite_est_acceptee_y_compris_dans_un_tableau():
    feature = FEATURE + '    Et je vois le tableau :\n      | client |\n      | {{client}} |\n'

    assert vdt.refus(feature, frozenset({"client", "ville"})) == []


def test_falsifiable_write_feature_file_refuse_une_variable_inconnue_quand_le_projet_en_declare(tmp_path):
    ctx = ToolContext(module_name="commande", generated_dir=tmp_path, variables_de_test=frozenset({"client"}))

    refuse = write_feature_file(ctx, FEATURE.replace("{{client}}", "{{pays}}"))
    assert not refuse.ok and "VARIABLE_DE_TEST" in refuse.observation and "pays" in refuse.observation
    assert not (tmp_path / "commande.feature").exists(), "refusé : rien n'est écrit"

    accepte = write_feature_file(ctx, FEATURE)
    assert accepte.ok, accepte.observation
    assert "{{client}}" in (tmp_path / "commande.feature").read_text(encoding="utf-8")


def test_falsifiable_interrupteur_eteint_l_ecriture_est_controlee_comme_avant(tmp_path):
    """Sans variable dans le contexte : aucun contrôle nouveau, et la référence reste confrontée aux enregistrements."""
    ctx = ToolContext(module_name="commande", generated_dir=tmp_path, options_select={"Client": {"Martin SARL"}})

    sortie = write_feature_file(ctx, FEATURE)

    assert not sortie.ok and "VARIABLE_DE_TEST" not in sortie.observation, "le refus d'avant (option inexistante)"


def test_une_valeur_variable_n_est_pas_confrontee_aux_enregistrements():
    options = {"Client": {"Martin SARL"}}

    assert verifier_references(FEATURE, options, {}, None) != [], "avant : refusée comme option inexistante"
    assert verifier_references(FEATURE, options, {}, None, ignorer_variables=True) == []


# ── 4. L'essai joue les valeurs du jeu « Par défaut » ─────────────────────────────────────────────────────────────────────


class _Runner:
    def __init__(self, dossier, joues):
        self.dossier, self.joues = dossier, joues

    def dry_run(self, module):
        return BehaveResult(success=True, returncode=0, dry_run=True)

    def real_run(self, module):
        self.joues.append((Path(self.dossier) / f"{module}.feature").read_text(encoding="utf-8"))
        return BehaveResult(success=True, returncode=0)


@pytest.fixture
def bac(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    bac_a_sable.reinitialiser_pour_les_tests()
    yield
    bac_a_sable.reinitialiser_pour_les_tests()


def _ctx(tmp_path, joues, valeurs):
    essai = e.EssaiBacASable(remettre_a_zero=lambda: None, cle="http://app:80",
                             fabriquer_runner=lambda dossier, variables: _Runner(dossier, joues))
    return ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=Annuaire(),
                       variables_de_test=frozenset({"client", "ville"}), valeurs_de_test=valeurs)


def test_falsifiable_l_essai_joue_les_valeurs_par_defaut(tmp_path, bac):
    joues: list[str] = []
    ctx = _ctx(tmp_path, joues, {"client": "Martin SARL"})

    sortie = dispatch(e.NOM_OUTIL, {"etapes": ['Quand je renseigne le champ "Client" avec la valeur "{{client}}"']}, ctx)

    assert sortie.ok, sortie.observation
    assert len(joues) == 1 and '"Martin SARL"' in joues[0] and "{{" not in joues[0]


def test_falsifiable_sans_valeur_par_defaut_l_essai_n_est_pas_joue(tmp_path, bac):
    joues: list[str] = []
    ctx = _ctx(tmp_path, joues, {"client": "Martin SARL"})

    sortie = dispatch(e.NOM_OUTIL, {"etapes": ['Quand je renseigne le champ "Ville" avec la valeur "{{ville}}"']}, ctx)

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation and "ville" in sortie.observation
    assert joues == []


def test_falsifiable_pt02f_sans_variable_permise_l_essai_ne_saisit_pas_une_variable(tmp_path, bac):
    """Lot PT-02f (revue du 2026-10-15) : dernière variable à la corbeille, le cas en cite une — rien n'est permis, et
    `{{client}}` aurait été saisi tel quel dans l'application."""
    joues: list[str] = []
    ctx = _ctx(tmp_path, joues, {})
    ctx.variables_de_test, ctx.controle_du_cas = frozenset(), True

    sortie = dispatch(e.NOM_OUTIL, {"etapes": ['Quand je renseigne le champ "Client" avec la valeur "{{client}}"']}, ctx)

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation and joues == []


# ── Revue du 2026-10-14 ───────────────────────────────────────────────────────────────────────────────────────────────────

STEPS_FAUX_VERT = '''from behave import then
from testpilot_steps import constater


@then("le client supprime n'apparait plus dans la liste")
def step_client_absent(context):
    texte = context.page.inner_text("body")
    constater("{{client}}" not in texte, "le client est encore affiche")
'''


def test_falsifiable_une_variable_dans_le_code_des_steps_est_refusee(tmp_path):
    """Le faux vert relevé : jamais remplacée dans le code, `"{{client}}" not in texte` serait toujours vrai."""
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, variables_de_test=frozenset({"client"}))

    sortie = dispatch("write_steps_file", {"content": STEPS_FAUX_VERT}, ctx)

    assert not sortie.ok and "VARIABLE_DE_TEST" in sortie.observation
    assert not (tmp_path / "m_steps.py").exists()


def test_interrupteur_eteint_le_code_des_steps_n_est_pas_controle_de_plus(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)

    sortie = dispatch("write_steps_file", {"content": STEPS_FAUX_VERT}, ctx)

    assert "VARIABLE_DE_TEST" not in sortie.observation


@pytest.mark.parametrize("ligne", ["Donc la page n'affiche pas le texte {{client}}",
                                   "Sachant que le client {{client}} existe",
                                   "Lorsqu'on saisit {{client}}"])
def test_falsifiable_tous_les_mots_d_etape_de_behave_sont_reconnus(ligne):
    feature = FEATURE.replace('    Alors la page affiche le texte "Commande enregistrée"', "    " + ligne)

    assert any("entre guillemets" in f for f in vdt.refus(feature, frozenset({"client"})))


def test_une_ligne_de_bloc_de_texte_n_est_pas_une_etape():
    feature = FEATURE + '    Et le message contient :\n      """\n      Et merci {{client}}\n      """\n'

    assert vdt.refus(feature, frozenset({"client"})) == []


def _ctx_de_reparation(tmp_path, reference: str) -> ToolContext:
    ctx = ToolContext(module_name="commande", generated_dir=tmp_path, options_select={"Client": {"Martin SARL"}})
    ctx.gel_feature = None   # le gel des vérifications est testé ailleurs : ici, seules les variables
    ctx.references_figees = vdt.references_du_texte(reference)
    return ctx


@pytest.mark.parametrize("ecrit, refuse", [
    (FEATURE, False),                                                   # inchangées
    (FEATURE.replace('"{{client}}"', '"Martin SARL"'), True),           # retirée (valeur en dur)
    (FEATURE.replace("{{client}}", "{{ville}}"), True),                 # renommée
    (FEATURE + '    Et je renseigne le champ "Ville" avec la valeur "{{ville}}"\n', True),   # ajoutée
])
def test_falsifiable_en_reparation_les_variables_sont_figees(tmp_path, ecrit, refuse):
    ctx = _ctx_de_reparation(tmp_path, FEATURE)

    sortie = write_feature_file(ctx, ecrit)

    assert ("VARIABLE_DE_TEST" in sortie.observation) is refuse, sortie.observation
    if not refuse:
        assert sortie.ok, "la valeur {{client}} n'est pas confrontée aux enregistrements existants"


def test_falsifiable_une_reparation_n_introduit_pas_de_variable_dans_un_test_qui_n_en_a_pas(tmp_path):
    sans = FEATURE.replace('"{{client}}"', '"Martin SARL"')
    ctx = _ctx_de_reparation(tmp_path, sans)

    assert "VARIABLE_DE_TEST" in write_feature_file(ctx, FEATURE).observation
    assert write_feature_file(ctx, sans).ok


def test_falsifiable_l_echec_d_un_essai_est_rendu_sans_la_valeur_posee(tmp_path, bac):
    from types import SimpleNamespace

    class _RunnerEnEchec(_Runner):
        def real_run(self, module):
            echec = SimpleNamespace(step_text='je renseigne le champ "Client" avec la valeur "Martin SARL"', page_url="",
                                    traceback_summary="", raw="")
            return BehaveResult(success=False, returncode=1, failures=[echec])

    essai = e.EssaiBacASable(remettre_a_zero=lambda: None, cle="http://app:80",
                             fabriquer_runner=lambda dossier, variables: _RunnerEnEchec(dossier, []))
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=Annuaire(),
                      variables_de_test=frozenset({"client"}), valeurs_de_test={"client": "Martin SARL"})

    sortie = dispatch(e.NOM_OUTIL, {"etapes": ['Quand je renseigne le champ "Client" avec la valeur "{{client}}"']}, ctx)

    assert "Martin SARL" not in sortie.observation and "{{client}}" in sortie.observation


def test_masquer_ne_touche_pas_une_valeur_d_un_seul_caractere():
    assert vdt.masquer("quantité 1, client Martin SARL", {"client": "Martin SARL", "quantite": "1"}) == \
        "quantité 1, client {{client}}"


def _generer(monkeypatch, tmp_path, projet):
    """Lance `GenerationAgent.generate` jusqu'à la boucle (simulée) : rend (premier message envoyé, contexte des outils)."""
    from types import SimpleNamespace

    from testpilot.analysis.plan import ScenarioIntent, TestPlan
    from testpilot.generation import agent as agent_mod

    vus = {}

    def capture(**kwargs):
        vus["message"] = kwargs["state"].messages[0]["content"]
        vus["ctx"] = kwargs["ctx"]

    monkeypatch.setattr(agent_mod.domain_model, "charger_modele", lambda projet: None)
    monkeypatch.setattr(agent_mod, "run_loop", capture)
    monkeypatch.setattr(agent_mod.config, "GENERATED_DIR", tmp_path)
    plan = TestPlan(module_name="m", models=[], scenarios=[ScenarioIntent(name="s", type="nominal", action="a",
                                                                          persona="p", expected_outcome="e")],
                    personas=["p"], portal_routes=[], risks=[], raw_spec="")
    try:
        agent_mod.GenerationAgent(llm=SimpleNamespace(), connector=None, dry_runner=None).generate(plan, projet=projet)
    except Exception:
        pass  # la suite de `generate` après la boucle n'intéresse pas ce test
    return vus["message"], vus["ctx"]


def test_falsifiable_interrupteur_eteint_un_projet_a_variables_envoie_le_message_d_avant(monkeypatch, tmp_path):
    sans = {"id": 1, "connector_type": "web"}
    avec = {**sans, **PROJET}

    message_sans, _ = _generer(monkeypatch, tmp_path, sans)
    message_avec, ctx = _generer(monkeypatch, tmp_path, avec)

    assert message_avec == message_sans, "octet pour octet"
    assert ctx.variables_de_test == frozenset() and ctx.valeurs_de_test == {}


def test_allume_le_message_annonce_les_noms_et_le_contexte_les_porte(monkeypatch, tmp_path, allume):
    message, ctx = _generer(monkeypatch, tmp_path, {"id": 1, "connector_type": "web", **PROJET})

    assert "{{client}}" in message and "Martin SARL" not in message
    assert ctx.variables_de_test == frozenset({"client", "ville"}) and ctx.valeurs_de_test["client"] == "Martin SARL"


# ── Revue du 2026-10-15 (deuxième passe) ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("variable", ["{{société}}", "{{Société}}", "{{ client }}", "{{client}"])
def test_falsifiable_toute_ecriture_de_variable_est_refusee_dans_le_code(tmp_path, variable):
    """Les noms accentués passaient la première version (motif ASCII) : même faux vert, `"{{société}}" not in texte`."""
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, variables_de_test=frozenset({"société", "client"}))
    code = STEPS_FAUX_VERT.replace("{{client}}", variable)

    sortie = dispatch("write_steps_file", {"content": code}, ctx)

    assert "VARIABLE_DE_TEST" in sortie.observation


@pytest.mark.parametrize("texte, attendu", [
    ("ville Lyonnais, ville Lyon.", "ville Lyonnais, ville {{ville}}."),         # mot entier seulement
    ("le {{client}} et Martin SARL", "le {{client}} et {{client}}"),             # une variable écrite n'est pas réécrite
    ("Martin SARL", "{{client}}"),                                               # la plus longue gagne
])
def test_masquer_en_un_seul_passage_et_en_mots_entiers(texte, attendu):
    assert vdt.masquer(texte, {"client": "Martin SARL", "ville": "Lyon", "court": "cl", "partiel": "Martin"}) == attendu


def test_masquer_dans_une_structure_ne_casse_jamais_un_nombre():
    donnees = {"execution_id": 146, "ok": None, "scenarios": [{"step_text": 'saisie "14" articles'}]}

    assert vdt.masquer_dans(donnees, {"quantite": "14"}) == {
        "execution_id": 146, "ok": None, "scenarios": [{"step_text": 'saisie "{{quantite}}" articles'}]}


def test_falsifiable_l_etape_inconnue_d_un_essai_est_rendue_sans_la_valeur(tmp_path, bac):
    class _RunnerABlanc(_Runner):
        def dry_run(self, module):
            return BehaveResult(success=False, returncode=1, dry_run=True,
                                undefined_steps=['je tape "Martin SARL" quelque part'])

    essai = e.EssaiBacASable(remettre_a_zero=lambda: None, cle="http://app:80",
                             fabriquer_runner=lambda dossier, variables: _RunnerABlanc(dossier, []))
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=Annuaire(),
                      variables_de_test=frozenset({"client"}), valeurs_de_test={"client": "Martin SARL"})

    sortie = dispatch(e.NOM_OUTIL, {"etapes": ['Quand je tape "{{client}}" quelque part']}, ctx)

    assert "STEP_INCONNU" in sortie.observation and "Martin SARL" not in sortie.observation


class _Arret(Exception):
    pass


@pytest.mark.parametrize("reference, figees", [(FEATURE, ["{{client}}"]), ("Fonctionnalité: X\n", [])])
def test_falsifiable_la_reparation_fige_les_variables_de_sa_reference(monkeypatch, tmp_path, reference, figees):
    from types import SimpleNamespace

    from testpilot.generation import repair_agent

    vus = {}

    def capture(**kwargs):
        vus["ctx"] = kwargs["ctx"]
        raise _Arret

    monkeypatch.setattr(repair_agent, "run_loop", capture)
    monkeypatch.setattr(repair_agent.config, "GENERATED_DIR", tmp_path)
    with pytest.raises(_Arret):
        repair_agent.propose_fix(module_name="m", scenarios=[], failures=[], llm=SimpleNamespace(), feature_content=reference)

    assert vus["ctx"].references_figees == figees


@pytest.mark.parametrize("reference, figees", [(FEATURE, ["{{client}}"]), ("Fonctionnalité: X\n", [])])
def test_falsifiable_la_correction_fige_les_variables_du_test_corrige(monkeypatch, tmp_path, reference, figees):
    from types import SimpleNamespace

    from testpilot.generation import correction_agent

    vus = {}

    def capture(**kwargs):
        vus["ctx"] = kwargs["ctx"]
        raise _Arret

    monkeypatch.setattr(correction_agent, "run_loop", capture)
    monkeypatch.setattr(correction_agent.config, "GENERATED_DIR", tmp_path)
    with pytest.raises(_Arret):
        correction_agent.propose_correction(module_name="m", lint_warnings=[], feature_content=reference, steps_content="",
                                            llm=SimpleNamespace())

    assert vus["ctx"].references_figees == figees


@pytest.mark.parametrize("interrupteur", [True, False])
def test_falsifiable_l_echec_renvoye_a_la_regeneration_masque_les_valeurs_jouees(monkeypatch, interrupteur):
    import json

    from testpilot.api.services import generation_service
    from testpilot.store import repositories

    if interrupteur:
        monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")
    echec = {"id": 146, "version_id": 7, "started_at": "", "error_message": 'champ "Client" : Martin SARL refusé',
             "execution_status": "technical_error", "functional_status": "", "artifacts_path": "",
             "parametres_joues": json.dumps({"jeu": "Par défaut", "valeurs": {"client": {"valeur": "Martin SARL"}}})}
    monkeypatch.setattr(repositories.ExecutionRepo, "list_for_case", lambda self, cid: [echec])
    monkeypatch.setattr(repositories.ExecutionRepo, "list_scenario_results", lambda self, eid: [
        {"scenario_name": "s", "step_text": 'je renseigne le champ "Client" avec la valeur "Martin SARL"',
         "error_summary": "", "execution_status": "technical_error", "functional_status": ""}])
    monkeypatch.setattr(repositories.RepairRepo, "list_for_execution", lambda self, eid: [])
    # Étape 5 (revue du 2026-10-22) : le dernier échec est pris sur une version qui porte un test — la version 7 en a un.
    monkeypatch.setattr(repositories.VersionRepo, "list_for_case", lambda self, cid: [{"id": 7, "feature_content": "# f"}])

    texte = generation_service._regeneration_failure_context(None, 1)[0]["text"]

    assert ("Martin SARL" in texte) is not interrupteur
    assert ('"execution_id": 146' in texte), "le reste du message intact"
