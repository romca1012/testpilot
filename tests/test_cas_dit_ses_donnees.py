"""Lot PT-02f (étape E2, décision A39) — le cas fait foi, aussi pour les données (interrupteur `TESTPILOT_CAS_DIT_SES_DONNEES`).

Ce que ces tests gardent :
1. interrupteur éteint : la rédaction des cas et le test technique sont ceux d'avant, octet pour octet ;
2. allumé : l'IA qui rédige les cas reçoit les NOMS des variables (jamais les valeurs) et peut écrire `{{nom}}` dans le texte
   du cas ; une variable inconnue, mal écrite ou dans le titre est refusée à la validation et à l'édition ;
3. le test technique reprend EXACTEMENT les variables que le cas cite : une manquante, ou une autre, est refusée à l'écriture
   (sans IA) ; une régénération garde celles que le test employait déjà (A41).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.generation import interrupteurs, metier_writer
from testpilot.generation import variables_de_test as vdt
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import write_feature_file

VARIABLES = [{"nom": "client", "description": "le client de la commande"}, {"nom": "ville", "description": ""}]
PROJET = {"id": 1, "connector_type": "web", "variables_de_test": VARIABLES,
          "valeurs_de_test_par_defaut": {"client": "Martin SARL", "ville": "Lyon"}}
METIER = {"title": "Commande", "preconditions": "", "steps": ["Saisir le client {{client}}", "Valider"],
          "expected_result": "La commande est enregistrée"}
FEATURE = """# language: fr
Fonctionnalité: Commande
  Scénario: Passer une commande
    Quand je renseigne le champ "Client" avec la valeur "{{client}}"
    Alors la page affiche le texte "Commande enregistrée"
"""


@pytest.fixture(autouse=True)
def eteints(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "0")
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "0")


def _allumer(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")


@pytest.fixture
def allume(monkeypatch):
    _allumer(monkeypatch)


def test_falsifiable_pt02f_sans_pt02d_ne_fait_rien(monkeypatch):
    """Revue du 2026-10-15, bloquant : PT-02f seul faisait écrire `{{client}}` dans les cas sans que le test technique (qui
    ne voit aucune variable sans PT-02d) soit obligé de l'employer — campagne « conforme » sur une valeur en dur."""
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")

    assert not interrupteurs.cas_dit_ses_donnees_actif()
    assert vdt.pour_les_cas(PROJET) == []


def _plan(spec="Une commande pour un client."):
    return TestPlan(module_name="m", models=[], scenarios=[ScenarioIntent(name="s", type="nominal", action="a", persona="p",
                                                                          expected_outcome="e")],
                    personas=["p"], portal_routes=[], risks=[], raw_spec=spec)


class _LLM:
    """Retient ce que l'IA qui rédige les cas a reçu."""

    def __init__(self):
        self.vus = []

    def call_json(self, **kwargs):
        self.vus.append(kwargs)
        return {"title": "Commande", "preconditions": "", "steps": ["Saisir le client {{client}}"],
                "expected_result": "Enregistrée", "depend_dun_autre_cas_du_groupe": False, "etat_a_creer_par_ce_cas": ""}


# ── 1-2. La rédaction des cas ─────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_eteint_la_redaction_des_cas_recoit_le_prompt_d_avant():
    assert vdt.pour_les_cas(PROJET) == []
    sans, avec = _LLM(), _LLM()

    metier_writer.propose_metier(_plan(), llm=sans)
    metier_writer.propose_metier(_plan(), llm=avec, variables=vdt.pour_les_cas(PROJET))

    assert avec.vus == sans.vus, "octet pour octet"


def test_allume_la_redaction_des_cas_recoit_les_noms_jamais_les_valeurs(allume):
    llm = _LLM()

    draft = metier_writer.propose_metier(_plan(), llm=llm, variables=vdt.pour_les_cas(PROJET))

    prefixe = llm.vus[0]["cached_prefix"]
    assert "{{client}}" in prefixe and "le client de la commande" in prefixe and "Martin SARL" not in prefixe
    assert prefixe.startswith(metier_writer._build_prompt(_plan())), "ajouté à la fin de la partie stable (cache)"
    assert draft.steps == ["Saisir le client {{client}}"], "l'écriture `{{nom}}` survit au nettoyage des étapes"


@pytest.mark.parametrize("metier, faute", [
    ({**METIER, "title": "Commande de {{client}}"}, "titre"),
    ({**METIER, "steps": ["Saisir {{pays}}"]}, "inconnue"),
    ({**METIER, "expected_result": "Le client {{client} est servi"}, "mal écrite"),
])
def test_falsifiable_un_texte_de_cas_mal_ecrit_est_refuse(metier, faute):
    fautes = vdt.refus_dans_le_cas(metier, ["client", "ville"])

    assert any(faute in f for f in fautes), fautes


def test_un_texte_de_cas_qui_cite_une_variable_du_projet_est_accepte():
    assert vdt.refus_dans_le_cas(METIER, ["client", "ville"]) == []
    assert vdt.variables_citees(METIER) == ["client"]


# ── 3. Le test technique reprend exactement les variables du cas ──────────────────────────────────────────────────────────


def test_eteint_le_test_technique_voit_toutes_les_variables_comme_avant():
    assert vdt.du_cas(VARIABLES, METIER) == (VARIABLES, frozenset(), False)


def test_allume_le_test_technique_ne_voit_que_les_variables_du_cas(allume):
    # Porteur, 2026-10-22 : les autres variables sont montrées pour PRÉPARER seulement (jamais requises, refusées en « Alors »).
    assert vdt.du_cas(VARIABLES, METIER) == ([VARIABLES[0], {**VARIABLES[1], "preparation": True}], frozenset({"client"}), True)
    assert vdt.du_cas(VARIABLES, METIER, ["ville"]) == (VARIABLES, frozenset({"client"}), True), "A41 : déjà dans le test"
    assert vdt.du_cas([], {**METIER, "steps": ["La page affiche {{ nom }}"]}) == ([], frozenset(), False), \
        "projet qui n'a JAMAIS déclaré de variable (gabarits) : son parcours ne change pas (revue, 3e passe)"
    assert vdt.du_cas([], {**METIER, "steps": ["Saisir"]}, ["client"], ["client"]) == ([], frozenset(), True), \
        "le test seul l'employait (A41), elle est à la corbeille : contrôle actif aussi"
    assert vdt.du_cas([], METIER, (), ["client"]) == ([], frozenset(), True), \
        "aucune variable vivante mais le cas en cite (corbeille) : rien de montré, toute écriture `{{…}}` refusée"
    assert vdt.du_cas([], {**METIER, "steps": ["Saisir"]}) == ([], frozenset(), False), "rien de cité, rien de vu : d'avant"
    assert vdt.du_cas(VARIABLES, None) == (VARIABLES, frozenset(), False), "sans cas (chemin CLI) : PT-02d seul"


def test_falsifiable_un_cas_qui_ne_cite_aucune_variable_n_en_requiert_aucune_et_ne_les_montre_que_pour_preparer(allume):
    """Règle d'avant (A39) : le cas ne cite rien, l'agent ne voyait rien. Porteur, 2026-10-22 : il les voit pour PRÉPARER
    (Soit, Quand) — aucune n'est requise, et une variable dans un « Alors » reste refusée (test plus bas)."""
    assert vdt.du_cas(VARIABLES, {**METIER, "steps": ["Saisir le client"]}) == (
        [{**v, "preparation": True} for v in VARIABLES], frozenset(), True)


def _ctx(tmp_path, permises, requises):
    return ToolContext(module_name="commande", generated_dir=tmp_path, variables_de_test=frozenset(permises),
                       variables_du_cas=frozenset(requises), controle_du_cas=True)


def test_falsifiable_un_test_qui_omet_une_variable_du_cas_est_refuse(tmp_path):
    """Sans ce contrôle, le test jouait « Martin SARL » en dur pour tous les jeux : le cas annonçait {{client}}, le test non."""
    sortie = write_feature_file(_ctx(tmp_path, {"client"}, {"client"}), FEATURE.replace('"{{client}}"', '"Martin SARL"'))

    assert not sortie.ok and "le cas emploie" in sortie.observation and "client" in sortie.observation
    assert not (tmp_path / "commande.feature").exists()


def test_falsifiable_un_test_qui_emploie_une_variable_que_le_cas_ne_cite_pas_est_refuse(tmp_path):
    sortie = write_feature_file(_ctx(tmp_path, set(), set()), FEATURE)

    assert not sortie.ok and "VARIABLE_DE_TEST" in sortie.observation and "le cas cite" in sortie.observation


def test_un_test_qui_reprend_exactement_les_variables_du_cas_est_accepte(tmp_path):
    sortie = write_feature_file(_ctx(tmp_path, {"client"}, {"client"}), FEATURE)

    assert sortie.ok, sortie.observation


def test_falsifiable_le_code_des_steps_est_controle_meme_sans_variable_du_cas(tmp_path):
    """Le faux vert du 2026-10-14 (`"{{client}}" not in page`, toujours vrai) : refusé aussi quand le cas n'en cite aucune."""
    from testpilot.generation.tools import dispatch

    code = 'from behave import then\n\n@then("ok")\ndef s(context):\n    assert "{{client}}" not in context.page.content()\n'
    sortie = dispatch("write_steps_file", {"content": code}, _ctx(tmp_path, set(), set()))

    assert "VARIABLE_DE_TEST" in sortie.observation


def _generer(monkeypatch, tmp_path, projet, metier):
    """`GenerationAgent.generate` jusqu'à la boucle (simulée) : (premier message, contexte des outils)."""
    from testpilot.generation import agent as agent_mod

    vus = {}

    def capture(**kwargs):
        vus["message"] = kwargs["state"].messages[0]["content"]
        vus["ctx"] = kwargs["ctx"]

    monkeypatch.setattr(agent_mod.domain_model, "charger_modele", lambda projet: None)
    monkeypatch.setattr(agent_mod, "run_loop", capture)
    monkeypatch.setattr(agent_mod.config, "GENERATED_DIR", tmp_path)
    try:
        agent_mod.GenerationAgent(llm=SimpleNamespace(), connector=None, dry_runner=None).generate(
            _plan(), projet=projet, metier=metier)
    except Exception:
        pass   # la suite de `generate` après la boucle n'intéresse pas ce test
    return vus["message"], vus["ctx"]


def test_falsifiable_pt02f_eteint_le_message_technique_est_celui_de_pt02d(monkeypatch, tmp_path):
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")
    message_avant, ctx_avant = _generer(monkeypatch, tmp_path, PROJET, METIER)

    assert "{{ville}}" in message_avant, "PT-02d seul : toutes les variables du projet"
    assert ctx_avant.variables_de_test == frozenset({"client", "ville"}) and not ctx_avant.controle_du_cas


def test_allume_le_message_technique_ne_montre_que_les_variables_du_cas(monkeypatch, tmp_path, allume):
    message, ctx = _generer(monkeypatch, tmp_path, PROJET, METIER)

    assert "{{client}}" in message
    preparation = message.split("Le cas ne cite pas ces autres données du projet")[1]
    assert "{{ville}}" in preparation and "{{ville}}" not in message.split("Le cas ne cite pas ces autres")[0]
    assert ctx.variables_de_test == frozenset({"client", "ville"}) and ctx.variables_du_cas == frozenset({"client"})
    assert ctx.variables_de_preparation == frozenset({"ville"})
    assert ctx.controle_du_cas


# ── Validation et édition par une personne ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(__import__("testpilot.api.app", fromlist=["app"]).app)


def _projet_et_cas(client):
    """Admin connecté, projet web à une variable `client`, un module et un cas manuel."""
    from testpilot.api import access
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import UserRepo

    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username="Root", password_hash=access.hacher_mot_de_passe("mdp"), role=access.ROLE_ADMIN)
    finally:
        conn.close()
    assert client.post("/api/auth/login", json={"username": "Root", "password": "mdp"}).status_code == 200
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web", "base_url": "https://a.test",
                                              "username": "u", "password": "p"}).json()["id"]
    client.post(f"/api/projects/{pid}/donnees-de-test/variables", json={"nom": "client"})
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Ventes"}).json()["id"]
    cas = client.post(f"/api/modules/{mid}/cases/manual",
                      json={"title": "Commande", "test_steps": ["Saisir le client"], "expected_result": "Enregistrée"})
    assert cas.status_code in (200, 201), cas.text
    return mid, cas.json()["id"]


@pytest.mark.parametrize("etape, attendu_allume", [("Saisir le client {{client}}", 200), ("Saisir {{pays}}", 422)])
def test_falsifiable_l_edition_d_un_cas_refuse_une_variable_inconnue_seulement_allume(client, monkeypatch, etape,
                                                                                    attendu_allume):
    import json

    _, cid = _projet_et_cas(client)
    corps = {"test_steps": json.dumps([etape], ensure_ascii=False)}

    assert client.patch(f"/api/cases/{cid}/metier", json={**corps, "expected_result": "A"}).status_code == 200, "éteint"
    _allumer(monkeypatch)
    assert client.patch(f"/api/cases/{cid}/metier", json={**corps, "expected_result": "B"}).status_code == attendu_allume


def test_falsifiable_la_creation_manuelle_refuse_une_variable_dans_le_titre(client, monkeypatch):
    mid, _ = _projet_et_cas(client)
    _allumer(monkeypatch)

    r = client.post(f"/api/modules/{mid}/cases/manual",
                    json={"title": "Commande {{client}}", "test_steps": ["Saisir"], "expected_result": "Ok"})

    assert r.status_code == 422 and "titre" in r.text


def test_falsifiable_la_validation_des_cas_proposes_refuse_une_variable_inconnue(client, monkeypatch):
    from testpilot.api.services import generation_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import GenerationJobRepo

    mid, _ = _projet_et_cas(client)
    _allumer(monkeypatch)
    conn = get_initialized_db(config.DB_PATH)
    try:
        GenerationJobRepo(conn).creer("j1", module_id=mid, payload={"title": "T", "spec_content": "S", "author": "a"})
        GenerationJobRepo(conn).maj("j1", status="awaiting_metier")
        cas = {"title": "Commande", "steps": ["Saisir {{pays}}"], "expected_result": "Ok"}
        with pytest.raises(generation_service.GenerationError, match="pays"):
            generation_service.validate_metier(conn, "j1", [cas])
        assert generation_service.validate_metier(conn, "j1", [{**cas, "steps": ["Saisir {{client}}"]}])["cases"]
    finally:
        conn.close()


def test_un_projet_sans_variable_garde_son_parcours_meme_allume(client, monkeypatch):
    """Revue du 2026-10-15 : un `{{ nom }}` (application à gabarits) dans un cas d'un projet SANS donnée de test reste du texte."""
    from testpilot.api import access
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import UserRepo

    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username="Root", password_hash=access.hacher_mot_de_passe("mdp"), role=access.ROLE_ADMIN)
    finally:
        conn.close()
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = client.post("/api/projects", json={"name": "Gabarits", "connector_type": "web", "base_url": "https://a.test",
                                              "username": "u", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Pages"}).json()["id"]
    _allumer(monkeypatch)

    r = client.post(f"/api/modules/{mid}/cases/manual",
                    json={"title": "Gabarit", "test_steps": ["Ouvrir"], "expected_result": "La page affiche {{ nom }}"})

    assert r.status_code in (200, 201), r.text


# ── Régénération (start_automation) ───────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def conn_cas(tmp_path, monkeypatch):
    """Un cas manuel dans un projet qui déclare `client` ; son test actuel emploie `{{client}}`."""
    import json

    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, TestDataRepo, VersionRepo, ensure_default_module

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "a.db")
    mid = ensure_default_module(conn, "m")
    TestDataRepo(conn).creer_variable(ModuleRepo(conn).get(mid)["project_id"], nom="client", description="")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="Commande", preconditions="",
                                       test_steps=json.dumps(["Saisir le client"]), expected_result="Enregistrée")
    version = VersionRepo(conn).get(CaseRepo(conn).get(cid)["current_version_id"])
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=FEATURE,
                                   steps_content="", title="Commande", preconditions="",
                                   test_steps=version["test_steps"], expected_result="Enregistrée")
    CaseRepo(conn).set_current_version(cid, vid)
    conn.commit()
    yield conn, cid
    conn.close()


def test_la_regeneration_garde_les_variables_du_test_actuel_seulement_allume(conn_cas, monkeypatch):
    """A41 : le cas ne cite pas {{client}} mais le test l'emploie (association d'un clic) — la régénération le sait."""
    from testpilot.api.services import generation_service

    conn, cid = conn_cas
    assert "variables_deja_dans_le_test" not in generation_service.start_automation(conn, cid)[1]["metier"], "éteint"
    _allumer(monkeypatch)

    assert generation_service.start_automation(conn, cid)[1]["metier"]["variables_deja_dans_le_test"] == ["client"]


def test_falsifiable_un_cas_qui_cite_une_variable_disparue_n_est_pas_genere(conn_cas, monkeypatch):
    """Revue du 2026-10-15 : la variable mise à la corbeille était ignorée en silence — le test jouait une valeur en dur."""
    import json

    from testpilot.api.services import generation_service
    from testpilot.store.repositories import CaseRepo

    conn, cid = conn_cas
    CaseRepo(conn).update_metier(cid, test_steps=json.dumps(["Saisir le pays {{pays}}"]))
    _allumer(monkeypatch)

    with pytest.raises(generation_service.GenerationError, match="pays"):
        generation_service.start_automation(conn, cid)


# ── Décision A42 : un écart entre le cas et son test bloque l'exécution ──────────────────────────────────────────────────


VERSION = {"feature_content": FEATURE.replace('"{{client}}"', '"Martin SARL"'), "preconditions": "",
           "test_steps": '["Saisir le client {{client}}"]', "expected_result": "Enregistrée"}


def test_falsifiable_l_ecart_cas_test_est_vu_seulement_allume(monkeypatch):
    assert vdt.ecart_cas_test(VERSION, ["client"]) == [], "éteint"
    _allumer(monkeypatch)

    assert vdt.ecart_cas_test(VERSION, ["client"]) == ["le cas cite « {{client}} », le test ne l'emploie pas"]
    assert vdt.ecart_cas_test({**VERSION, "feature_content": FEATURE}, ["client"]) == [], "le test l'emploie"
    assert vdt.ecart_cas_test(VERSION, []) == [], "projet sans donnée de test : son parcours ne change pas"
    assert vdt.ecart_cas_test({**VERSION, "feature_content": ""}, ["client"]) == [], "pas encore de test"
    inverse = {**VERSION, "feature_content": FEATURE, "test_steps": '["Saisir le client"]'}
    assert vdt.ecart_cas_test(inverse, ["client"]) == [], "le test emploie une variable que le cas ne cite pas : A41"


def test_falsifiable_l_ecart_bloque_meme_une_version_approuvee():
    from testpilot.verdict import review_gate

    approuvee = review_gate.GateDecision(allowed=True, needs_review=False, reason="version approuvée en relecture")

    assert review_gate.bloquer_si_ecart(approuvee, []) is approuvee
    bloquee = review_gate.bloquer_si_ecart(approuvee, ["le cas cite « {{client}} », le test ne l'emploie pas"])
    assert not bloquee.allowed and "{{client}}" in bloquee.reason


def test_falsifiable_editer_le_cas_sans_le_test_bloque_l_approbation_et_l_execution(client, monkeypatch):
    """Le scénario de la revue : le test saisit « Martin SARL » en dur, une personne écrit {{client}} dans le cas — la nouvelle
    version n'est pas approuvée d'office, ne s'approuve pas, ne s'exécute pas ; la fiche dit pourquoi."""
    import json

    _, cid = _projet_et_cas(client)
    script = client.patch(f"/api/cases/{cid}/script", json={"feature_content": VERSION["feature_content"],
                                                            "steps_content": "# steps\n"})
    assert script.status_code == 200, script.text
    assert client.post(f"/api/cases/{cid}/review", json={"approved": True}).status_code == 200
    _allumer(monkeypatch)

    assert client.patch(f"/api/cases/{cid}/metier",
                        json={"test_steps": json.dumps(["Saisir le client {{client}}"])}).status_code == 200

    gate = client.get(f"/api/cases/{cid}").json()["gate"]
    assert gate["allowed"] is False and "{{client}}" in gate["reason"]
    approbation = client.post(f"/api/cases/{cid}/review", json={"approved": True})
    assert approbation.status_code == 409 and "écart" in approbation.text
    lancement = client.post(f"/api/cases/{cid}/runs")
    assert lancement.status_code >= 400 and "écart" in lancement.text, lancement.text
    a_relire = client.get("/api/cases/needing-review", params={"project_id": client.get(f"/api/cases/{cid}").json()
                                                               ["case"]["project_id"]}).json()
    assert [c["case_id"] for c in a_relire] == [cid] and "{{client}}" in a_relire[0]["reason"], "trouvable, raison juste"
    # Jamais approuvée d'office : PT-02f éteint, la version reste à relire (revue du 2026-10-15, 2e passe).
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "0")
    assert client.get(f"/api/cases/{cid}").json()["gate"]["allowed"] is False


def test_falsifiable_la_derniere_variable_a_la_corbeille_ne_desactive_rien(conn_cas, monkeypatch):
    """Revue du 2026-10-15, 2e passe, bloquant : l'unique variable à la corbeille, le cas qui la cite se régénérait sans
    aucun contrôle — l'agent pouvait écrire `"{{client}}" not in page` (toujours vrai) ou une valeur en dur."""
    import json

    from testpilot.api.services import generation_service, run_service
    from testpilot.store.repositories import CaseRepo, ModuleRepo, TestDataRepo

    conn, cid = conn_cas
    CaseRepo(conn).update_metier(cid, test_steps=json.dumps(["Supprimer le client {{client}}"]))
    pid = ModuleRepo(conn).get(CaseRepo(conn).get(cid)["module_id"])["project_id"]
    depot = TestDataRepo(conn)
    depot.supprimer_variable(pid, next(v["id"] for v in depot.variables(pid) if v["nom"] == "client"))
    _allumer(monkeypatch)

    with pytest.raises(generation_service.GenerationError, match="client"):
        generation_service.start_automation(conn, cid)
    cas = CaseRepo(conn).get(cid)
    version_en_dur = {"feature_content": FEATURE.replace('"{{client}}"', '"Martin SARL"')}
    conn.execute("UPDATE test_case_version SET feature_content=? WHERE id=?",
                 (version_en_dur["feature_content"], cas["current_version_id"]))
    conn.commit()
    assert run_service.ecarts_cas_test(conn, cas, cas["current_version_id"]), "l'écart reste vu"


def test_falsifiable_une_version_approuvee_qui_devient_en_ecart_est_listee_a_relire(client, monkeypatch):
    """Revue du 2026-10-15, 3e passe : le cas citait {{client}} avant que le projet la déclare ; la version, approuvée, se
    retrouve en écart — bloquée ET trouvable dans la liste « à relire », avec la raison."""
    import json

    from testpilot.store.db import get_initialized_db

    _, cid = _projet_et_cas(client)
    pid = client.get(f"/api/cases/{cid}").json()["case"]["project_id"]
    conn = get_initialized_db(config.DB_PATH)
    try:   # le projet n'a encore déclaré aucune variable
        conn.execute("DELETE FROM test_variable WHERE project_id=?", (pid,))
        conn.commit()
    finally:
        conn.close()
    _allumer(monkeypatch)
    assert client.patch(f"/api/cases/{cid}/metier", json={"test_steps": json.dumps(["Saisir le client {{client}}"]),
                                                          "expected_result": "Ok"}).status_code == 200
    assert client.patch(f"/api/cases/{cid}/script", json={"feature_content": VERSION["feature_content"],
                                                          "steps_content": "# steps"}).status_code == 200
    assert client.post(f"/api/cases/{cid}/review", json={"approved": True}).status_code == 200, "sans variable : pas d'écart"

    client.post(f"/api/projects/{pid}/donnees-de-test/variables", json={"nom": "client"})

    a_relire = client.get("/api/cases/needing-review", params={"project_id": pid}).json()
    assert [c["case_id"] for c in a_relire] == [cid] and "{{client}}" in a_relire[0]["reason"]
    assert "écart" in client.post(f"/api/cases/{cid}/runs").text



# ── Porteur, 2026-10-22 : une variable que le cas ne cite pas sert à PRÉPARER, jamais à VÉRIFIER ─────────────────────────


def _ctx_preparation(tmp_path):
    return ToolContext(module_name="commande", generated_dir=tmp_path, variables_de_test=frozenset({"client", "ville"}),
                       variables_du_cas=frozenset({"client"}), controle_du_cas=True,
                       variables_de_preparation=frozenset({"ville"}))


def test_une_variable_de_preparation_est_permise_dans_un_soit_ou_un_quand(tmp_path):
    feature = FEATURE.replace('    Quand je renseigne', '    Soit je renseigne le champ "Ville" avec la valeur "{{ville}}"\n'
                                                        '    Quand je renseigne')
    sortie = write_feature_file(_ctx_preparation(tmp_path), feature)
    assert sortie.ok, sortie.observation


def test_falsifiable_une_variable_de_preparation_dans_un_alors_est_refusee(tmp_path):
    feature = FEATURE.replace('Alors la page affiche le texte "Commande enregistrée"',
                              'Alors la page affiche le texte "Commande enregistrée"\n    Et la page affiche le texte "{{ville}}"')
    sortie = write_feature_file(_ctx_preparation(tmp_path), feature)
    assert not sortie.ok and "« {{ville}} » dans un « Alors »" in sortie.observation, sortie.observation
