"""IT-3c (décisions A53, A58, A60, porteur, 2026-10-19) — l'IA qui rédige les cas PROPOSE les lignes d'un cas (classes de
valeurs, valeurs limites, résultat attendu de chacune) pour les seules variables déjà déclarées dans le projet ; une personne
les relit et les valide avec le cas ; elles deviennent ses lignes, et sa génération les emploie.

Ce que ces tests gardent :
1. interrupteur éteint : schéma, consigne et brouillon d'avant, octet pour octet ;
2. allumé : la consigne n'expose que des NOMS de variables ; ce que l'IA rend est nettoyé sans rien inventer (variable
   inconnue, valeur qui casserait le test, doublon, ligne vide : écartés — A60) ;
3. la validation refuse une ligne invalide en le disant, et transporte les lignes valides ;
4. à la génération : les lignes deviennent celles du cas AVANT les points de vigilance, l'agent reçoit leurs noms dans le
   métier et la première ligne en valeurs d'essai — jamais dans le métier.
Aucun appel au modèle de langage : des doublures.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.generation import interrupteurs, metier_writer

VARIABLES = [{"nom": "age", "description": "âge saisi"}, {"nom": "resultat", "description": "message attendu"}]


def _plan():
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[],
                    raw_spec="Moins de 18 ans : accès refusé.")


class _IA:
    """Une doublure de `LLMAdapter.call_json` : garde ce qu'on lui envoie, rend une réponse fixée."""

    def __init__(self, reponse):
        self.reponse, self.appels = reponse, []

    def call_json(self, **kw):
        self.appels.append(kw)
        return self.reponse


BASE = {"title": "Accès selon l'âge", "preconditions": "", "steps": ["Saisir l'âge {{age}}"],
        "expected_result": "{{resultat}}", "depend_dun_autre_cas_du_groupe": False, "etat_a_creer_par_ce_cas": ""}


def test_falsifiable_eteint_tout_est_comme_avant():
    ia = _IA(dict(BASE, lignes=[{"nom": "x", "valeurs": [{"variable": "age", "valeur": "17"}]}]))
    brouillon = metier_writer.propose_metier(_plan(), llm=ia, variables=VARIABLES)

    assert ia.appels[0]["schema"] is metier_writer._METIER_SCHEMA
    assert ia.appels[0]["max_tokens"] == 2000
    assert ia.appels[0]["cached_prefix"] == metier_writer._build_prompt(_plan()) + metier_writer._section_variables(VARIABLES)
    assert brouillon.lignes == [] and "lignes" not in brouillon.as_dict()


def test_falsifiable_allume_la_consigne_ne_montre_que_des_noms_et_les_lignes_sont_nettoyees():
    # Revue du 2026-10-19 (changement délibéré de l'attendu) : une ligne dont UNE valeur est refusée est écartée EN ENTIER
    # — amputée de son résultat attendu, « 17 ans » aurait été jouée en attendant la valeur du projet.
    def paires(age, resultat):
        return [{"variable": "age", "valeur": age}, {"variable": "resultat", "valeur": resultat}]

    reponse = dict(BASE, lignes=[
        {"nom": "Juste mineur", "valeurs": paires("17", "Refusé")},
        {"nom": "Inventée", "valeurs": paires("18", "Oui") + [{"variable": "inventee", "valeur": "x"}]},
        {"nom": "Guillemet", "valeurs": paires("19", '"Non"')},                           # casserait le test : écartée
        {"nom": "juste  MINEUR", "valeurs": paires("16", "Refusé")},                      # nom en double : écartée
        {"nom": "Ligne 1", "valeurs": paires("18", "Bienvenue")},                         # nom d'office : retiré
        {"nom": "Même contenu", "valeurs": paires("18", "Bienvenue")},                    # contenu en double : écartée
        # 2e passe : une variable omise, ou laissée vide — jamais une reprise voulue de la valeur du projet.
        {"nom": "Sans résultat", "valeurs": [{"variable": "age", "valeur": "20"}]},
        {"nom": "Résultat vide", "valeurs": paires("21", "")},
        {"nom": "Vide", "valeurs": []},
    ])
    ia = _IA(reponse)

    brouillon = metier_writer.propose_metier(_plan(), llm=ia, variables=VARIABLES, proposer_lignes=True)

    consigne = ia.appels[0]["cached_prefix"]
    assert "LIGNES DU CAS" in consigne and "valeurs limites" in consigne and ia.appels[0]["schema"]["required"][-1] == "lignes"
    assert brouillon.lignes == [{"nom": "Juste mineur", "valeurs": {"age": "17", "resultat": "Refusé"}},
                                {"nom": "", "valeurs": {"age": "18", "resultat": "Bienvenue"}}], \
        "lignes amputées, incomplètes, doublons, vides : écartées"
    assert brouillon.as_dict()["lignes"] == brouillon.lignes


def test_l_interrupteur_suppose_pt02f(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_LIGNES_PROPOSEES, "1")
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "0")
    assert not interrupteurs.lignes_proposees_actif()
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")
    assert interrupteurs.lignes_proposees_actif()
    monkeypatch.delenv(interrupteurs.ENV_LIGNES_PROPOSEES)
    assert not interrupteurs.lignes_proposees_actif(), "éteint par défaut"


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import GenerationJobRepo, ModuleRepo, ProjectRepo, TestDataRepo

    db = tmp_path / "db.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(db)
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    ids = {n: TestDataRepo(conn).creer_variable(pid, nom=n) for n in ("age", "resultat")}
    GenerationJobRepo(conn).creer("j", module_id=mid, payload={"title": "T", "spec_content": "spec", "author": "a"})
    conn.execute("UPDATE generation_job SET status='awaiting_metier' WHERE id='j'")
    conn.commit()
    yield conn, pid, mid, ids
    conn.close()


def _cas(**plus):
    return {"title": "Accès selon l'âge", "steps": ["Saisir l'âge"], "expected_result": "Le message s'affiche", **plus}


@pytest.mark.parametrize("lignes, motif", [
    ([{"nom": "A", "valeurs": {"inconnue": "1"}}], "n'est pas une variable du projet"),
    ([{"nom": "A", "valeurs": {"age": 'a"b'}}], "ligne « A »"),
    ([{"nom": "A", "valeurs": {"age": "1"}}, {"nom": "a", "valeurs": {"age": "2"}}], "deux lignes"),
    # Revue du 2026-10-19 : les règles de la fiche du cas, exactement — refusées ICI, plus après la création du cas.
    ([{"nom": "Juste  mineur", "valeurs": {"age": "1"}}, {"nom": "Juste mineur", "valeurs": {"age": "2"}}], "deux lignes"),
    ([{"nom": "Ligne 2", "valeurs": {"age": "1"}}], "nom donné d'office"),
    ([{"nom": "x" * 61, "valeurs": {"age": "1"}}], "trop long"),
])
def test_falsifiable_la_validation_refuse_une_ligne_invalide_en_le_disant(projet, lignes, motif):
    from testpilot.api.services import generation_service

    conn, *_ = projet
    with pytest.raises(generation_service.GenerationError, match=motif):
        generation_service.validate_metier(conn, "j", [_cas(lignes=lignes)])


def test_la_validation_transporte_les_lignes_valides(projet):
    from testpilot.api.services import generation_service

    conn, *_ = projet
    lignes = [{"nom": "Juste mineur", "valeurs": {"age": "17", "resultat": "Refusé"}}]
    sortie = generation_service.validate_metier(conn, "j", [_cas(lignes=lignes), _cas(title="Sans ligne")])
    assert sortie["cases"][0]["lignes"] == lignes and "lignes" not in sortie["cases"][1]


def test_falsifiable_a_la_generation_les_lignes_deviennent_celles_du_cas_et_l_agent_les_emploie(projet, monkeypatch):
    from testpilot.analysis.plan import TestPlan
    from testpilot.api.services import generation_service
    from testpilot.store.repositories import CaseDataRepo, CaseRepo

    conn, pid, mid, _ = projet
    vus = {}

    class _Agent:
        def __init__(self, **kw):
            pass

        def generate(self, plan, **kw):
            from testpilot.store.db import get_initialized_db
            c = get_initialized_db(config.DB_PATH)
            cid = CaseRepo(c).create(title=kw["title"], module_id=mid, feature_slug=plan.module_name)
            c.close()
            vus.update(kw, case_id=cid)
            return SimpleNamespace(success=True, case_id=cid, version_id=None, cost_usd=0.0, error="", stopped_reason="")

    class _Analyse:
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[])

    class _Connecteur:
        def connect(self):
            pass

        def disconnect(self):
            pass

    def _finaliser(c, case_id, version_id, **kw):
        vus["lignes_au_finaliser"] = CaseDataRepo(c).niveaux(case_id)

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.connectors.factory as factory
    import testpilot.connectors.runtime_env as runtime_env
    import testpilot.execution.behave_runner as behave_runner
    import testpilot.generation.agent as agent_mod
    monkeypatch.setattr(agent_mod, "GenerationAgent", _Agent)
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    monkeypatch.setattr(factory, "build_connector", lambda projet: _Connecteur())
    monkeypatch.setattr(runtime_env, "env_du_projet", lambda *a, **k: {})
    monkeypatch.setattr(behave_runner, "BehaveRunner", lambda **kw: object())
    monkeypatch.setattr(generation_service, "_finaliser_version_generee", _finaliser)

    lignes = [{"nom": "Juste mineur", "valeurs": {"age": "17", "resultat": "Refusé"}},
              {"nom": "Majeur", "valeurs": {"age": "18", "resultat": "Bienvenue"}}]
    generation_service.resume_generation("j", module_id=mid, title="T", spec_content="spec", author="a",
                                         cases=[{**_cas(lignes=lignes), "preconditions": "", "user_story": ""}])

    assert vus["metier"]["variables_des_lignes"] == ["age", "resultat"]
    assert vus["valeurs_d_essai"] == {"age": "17", "resultat": "Refusé"}
    assert "17" not in str(vus["metier"]) and "Refusé" not in str(vus["metier"]), "aucune valeur dans le métier"
    attendu = [("Juste mineur", {"age": "17", "resultat": "Refusé"}), ("Majeur", {"age": "18", "resultat": "Bienvenue"})]
    assert vus["lignes_au_finaliser"] == attendu, "les lignes existent AVANT les points de vigilance"
    assert CaseDataRepo(conn).niveaux(vus["case_id"]) == attendu


@pytest.mark.parametrize("allume", [False, True])
def test_falsifiable_la_generation_ne_demande_les_lignes_qu_interrupteur_allume(projet, monkeypatch, allume):
    """Câblage : `run_generation` passe `proposer_lignes` à l'IA des cas seulement interrupteur allumé, et les lignes
    proposées arrivent dans le job, à relire."""
    from testpilot.analysis.plan import TestPlan
    from testpilot.api.services import generation_service
    from testpilot.store.repositories import GenerationJobRepo

    conn, pid, mid, _ = projet
    monkeypatch.setenv(interrupteurs.ENV_LIGNES_PROPOSEES, "1" if allume else "0")
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")
    appels = []

    class _Analyse:
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[])

    def _metier(plan, **kw):
        appels.append(kw)
        return metier_writer.MetierDraft(title="Accès", steps=["Saisir"], expected_result="Message",
                                         lignes=[{"nom": "Limite", "valeurs": {"age": "18"}}] if kw.get("proposer_lignes") else [])

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.generation.decoupage as decoupage
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    monkeypatch.setattr(decoupage, "propose_decoupage", lambda plan, **kw: [
        SimpleNamespace(user_story="US", cases=[SimpleNamespace(brief="b", title="Accès")])])
    monkeypatch.setattr(metier_writer, "propose_metier", _metier)

    generation_service.run_generation("j", module_id=mid, title="T", spec_content="spec", author="a")

    assert bool(appels[0].get("proposer_lignes")) is allume
    cas = GenerationJobRepo(conn).get("j")["cases"]
    assert (cas[0].get("lignes") == [{"nom": "Limite", "valeurs": {"age": "18"}}]) is allume



def test_falsifiable_une_variable_mise_a_la_corbeille_avant_la_generation_arrete_ce_cas_seul(projet, monkeypatch):
    """Revue du 2026-10-19 : écarter la colonne laissait des lignes vides, jouées sous leurs noms avec une même valeur."""
    from testpilot.api.services import generation_service
    from testpilot.store.repositories import GenerationJobRepo, TestDataRepo

    conn, pid, mid, ids = projet
    TestDataRepo(conn).supprimer_variable(pid, ids["age"], par="x")
    vus = _doublures(monkeypatch, generation_service, mid)

    generation_service.resume_generation("j", module_id=mid, title="T", spec_content="spec", author="a", cases=[
        {**_cas(lignes=[{"nom": "Juste mineur", "valeurs": {"age": "17"}}]), "preconditions": "", "user_story": ""},
        {**_cas(title="Autre"), "preconditions": "", "user_story": ""}])

    assert vus["titres"] == ["Autre"], "le cas aux lignes disparues n'est pas généré ; l'autre l'est"
    assert vus["finalises"] == ["Autre"]
    assert "{{age}}" in (GenerationJobRepo(conn).get("j").get("error") or "")


def test_falsifiable_un_refus_des_lignes_apres_la_creation_ne_touche_que_ce_cas(projet, monkeypatch):
    from testpilot.api.services import generation_service
    from testpilot.store.repositories import GenerationJobRepo

    conn, pid, mid, _ = projet
    vus = _doublures(monkeypatch, generation_service, mid)

    generation_service.resume_generation("j", module_id=mid, title="T", spec_content="spec", author="a", cases=[
        {**_cas(lignes=[{"nom": "Ligne 2", "valeurs": {"age": "17"}}]), "preconditions": "", "user_story": ""},
        {**_cas(title="Autre"), "preconditions": "", "user_story": ""}])

    job = GenerationJobRepo(conn).get("j")
    assert sorted(vus["titres"]) == sorted(["Accès selon l'âge", "Autre"]), "les cas tournent en parallèle"
    assert vus["finalises"] == ["Autre"], "le cas privé de ses lignes n'est jamais finalisé (ni approuvé)"
    assert len(job.get("case_ids") or []) == 1, "l'autre cas aboutit ; le lot n'échoue pas en entier"
    assert "ses lignes n'ont pas pu être enregistrées" in (job.get("error") or "")


def _doublures(monkeypatch, generation_service, mid):
    from testpilot.analysis.plan import TestPlan
    from testpilot.store.repositories import CaseRepo

    vus = {"titres": [], "finalises": []}

    class _Agent:
        def __init__(self, **kw):
            pass

        def generate(self, plan, **kw):
            from testpilot.store.db import get_initialized_db
            c = get_initialized_db(config.DB_PATH)
            cid = CaseRepo(c).create(title=kw["title"], module_id=mid, feature_slug=plan.module_name)
            c.close()
            vus["titres"].append(kw["title"])
            if kw["title"] == "Pendant" and vus.get("pendant"):
                vus["pendant"]()   # une variable part à la corbeille PENDANT la génération
            return SimpleNamespace(success=True, case_id=cid, version_id=None, cost_usd=0.0, error="", stopped_reason="")

    class _Analyse:
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[])

    class _Connecteur:
        def connect(self):
            pass

        def disconnect(self):
            pass

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.connectors.factory as factory
    import testpilot.connectors.runtime_env as runtime_env
    import testpilot.execution.behave_runner as behave_runner
    import testpilot.generation.agent as agent_mod
    monkeypatch.setattr(agent_mod, "GenerationAgent", _Agent)
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    monkeypatch.setattr(factory, "build_connector", lambda projet: _Connecteur())
    monkeypatch.setattr(runtime_env, "env_du_projet", lambda *a, **k: {})
    monkeypatch.setattr(behave_runner, "BehaveRunner", lambda **kw: object())
    def _finaliser(c, case_id, version_id, **kw):
        vus["finalises"].append(CaseRepo(c).get(case_id)["title"])

    monkeypatch.setattr(generation_service, "_finaliser_version_generee", _finaliser)
    return vus



def test_falsifiable_une_variable_mise_a_la_corbeille_pendant_la_generation_n_arrete_que_ce_cas(projet, monkeypatch):
    """Revue, 2e passe : vérifiée avant la génération, la variable peut partir pendant (des minutes) — un `KeyError`
    faisait alors échouer tout le lot."""
    from testpilot.api.services import generation_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import GenerationJobRepo, TestDataRepo

    conn, pid, mid, ids = projet
    vus = _doublures(monkeypatch, generation_service, mid)

    def _corbeille():
        c = get_initialized_db(config.DB_PATH)
        TestDataRepo(c).supprimer_variable(pid, ids["age"], par="x")
        c.close()

    vus["pendant"] = _corbeille
    generation_service.resume_generation("j", module_id=mid, title="T", spec_content="spec", author="a", cases=[
        {**_cas(title="Pendant", lignes=[{"nom": "Juste mineur", "valeurs": {"age": "17"}}]), "preconditions": "",
         "user_story": ""},
        {**_cas(title="Autre"), "preconditions": "", "user_story": ""}])

    job = GenerationJobRepo(conn).get("j")
    assert vus["finalises"] == ["Autre"] and len(job.get("case_ids") or []) == 1
    assert "{{age}}" in (job.get("error") or "") and "corbeille" in (job.get("error") or "")



def test_falsifiable_une_ligne_aberrante_ne_fait_pas_ecarter_les_bonnes():
    """Revue, 3e passe : la référence est l'ensemble de variables de la MAJORITÉ des lignes ; égalité : aucune ligne."""
    variables = VARIABLES + [{"nom": "client", "description": ""}]

    def ligne(nom, **valeurs):
        return {"nom": nom, "valeurs": [{"variable": k, "valeur": v} for k, v in valeurs.items()]}

    brutes = [ligne("A", age="16", resultat="Refusé"), ligne("B", age="17", resultat="Refusé"),
              ligne("C", age="18", resultat="Bienvenue"), ligne("D", age="19", resultat="Bienvenue", client="X")]
    assert [l["nom"] for l in metier_writer.lignes_propres(brutes, [v["nom"] for v in variables])] == ["A", "B", "C"]
    egalite = [ligne("A", age="16"), ligne("B", age="17", resultat="Refusé")]
    assert metier_writer.lignes_propres(egalite, [v["nom"] for v in variables]) == [], "égalité : rien, plutôt que deviner"
    # un doublon de nom porté par une ligne écartée ne fait plus écarter la bonne
    homonymes = [ligne("Limite", age="18", client="X"), ligne("Limite", age="18", resultat="Bienvenue"),
                 ligne("Autre", age="17", resultat="Refusé")]
    assert [l["nom"] for l in metier_writer.lignes_propres(homonymes, [v["nom"] for v in variables])] == ["Limite", "Autre"]
