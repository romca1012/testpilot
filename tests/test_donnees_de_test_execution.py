"""Lot PT-02b — les données de test au LANCEMENT d'une exécution (décisions A26 à A29).

Ce que ces tests gardent :
1. un projet sans variable joue exactement comme aujourd'hui — même fichier, rien de consigné, même avec des `{{…}}` dans le
   test (un modèle de courriel d'Odoo en contient) ;
2. un test qui écrit `{{nom}}` est joué depuis une COPIE propre à son exécution, valeurs posées ; le fichier partagé du cas
   n'est jamais touché, deux exécutions ne se mélangent pas ;
3. une valeur qui manque (variable inconnue, sans valeur, mal écrite) : le cas n'est PAS joué, il sort « bloqué » avec la
   variable nommée — jamais « conforme », jamais `{{nom}}` saisi dans l'application ;
4. les valeurs d'une campagne sont figées au lancement : modifier le tableau ensuite, ou relancer, ne change rien (A29) ;
   un jeu à la corbeille empêche le lancement ;
5. un test joué avec des valeurs posées n'est pas réparé automatiquement (la réparation réécrirait le test générique).
"""

import json

import pytest

from testpilot import config
from testpilot.api.services import campaign_service, donnees_de_test_service as service, run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, RunRepo, TestDataRepo, VersionRepo,
)
from testpilot.verdict import status as st

FEATURE = """# language: fr
Fonctionnalité: Commande
  Scénario: Passer une commande
    Quand je saisis le client "{{client}}" à "{{ville}}"
    Alors la page affiche le texte "Commande de {{client}}"
"""
STEPS = "from behave import then\n"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _cas(conn, feature: str = FEATURE, *, variables: dict | None = None):
    """Un projet, un cas dont la version courante écrit `feature`, et (facultatif) des variables avec leur valeur par défaut."""
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"),
                                feature_slug="commande")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature, steps_content=STEPS)
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    ids = {nom: depot.creer_variable(pid, nom=nom) for nom in (variables or {})}
    if variables:
        depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ids[n]: v for n, v in variables.items()})
    return pid, cid, vid, ids


def _execution(conn, cid, vid, run_id=None) -> int:
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    if run_id is not None:
        conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
        conn.commit()
    return eid


def _joues(conn, eid) -> str:
    return conn.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0]


# ── 1. Rien ne change pour un projet sans variable ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("feature", [FEATURE, "Fonctionnalité: X\n  Scénario: Y\n    Alors le courriel contient \"{{ object.partner_id.name }}\"\n"])
def test_falsifiable_un_projet_sans_variable_joue_comme_aujourd_hui(base, feature):
    pid, cid, vid, _ = _cas(base, feature)
    eid = _execution(base, cid, vid)

    script = service.preparer_le_script(base, eid, cid, vid, "commande")

    assert script == service.Script(), "le chemin d'aujourd'hui : aucun dossier propre, aucun blocage"
    assert _joues(base, eid) == ""
    assert not (config.DATA_DIR / "executions").exists()


# ── 2. Les valeurs posées dans une copie propre à l'exécution ─────────────────────────────────────────────────────────────


def test_un_cas_lance_seul_joue_le_jeu_par_defaut_dans_sa_propre_copie(base):
    pid, cid, vid, _ = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    run_service._assurer_script_sur_disque(base, vid, "commande")
    eid = _execution(base, cid, vid)

    script = service.preparer_le_script(base, eid, cid, vid, "commande")

    assert script.blocage == "" and script.dossier == config.DATA_DIR / "executions" / str(eid) / "script"
    joue = (script.dossier / "commande.feature").read_text(encoding="utf-8")
    assert joue == FEATURE.replace("{{client}}", "Martin SARL").replace("{{ville}}", "Lyon")
    assert (script.dossier / "commande_steps.py").read_text(encoding="utf-8") == STEPS
    assert (config.GENERATED_DIR / "commande.feature").read_text(encoding="utf-8") == FEATURE, "le fichier partagé reste générique"
    assert json.loads(_joues(base, eid)) == {"jeu": "Par défaut", "valeurs": {
        "client": {"valeur": "Martin SARL", "origine": "Par défaut"}, "ville": {"valeur": "Lyon", "origine": "Par défaut"}}}


def test_falsifiable_deux_executions_avec_deux_jeux_ne_se_melangent_pas(base):
    pid, cid, vid, ids = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    depot = TestDataRepo(base)
    grosse = depot.creer_jeu(pid, nom="Grosse commande")
    depot.poser_valeurs(pid, grosse, {ids["client"]: "Durand Industrie"})
    runs = []
    for jeu in (None, grosse):
        run_id = RunRepo(base).create(project_id=pid, name=f"Campagne {jeu}", case_ids=[cid])
        base.execute("UPDATE test_run SET dataset_id=? WHERE id=?", (jeu, run_id))
        base.commit()
        service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
        runs.append(run_id)
    e1, e2 = _execution(base, cid, vid, runs[0]), _execution(base, cid, vid, runs[1])

    s1, s2 = (service.preparer_le_script(base, e, cid, vid, "commande") for e in (e1, e2))

    t1, t2 = ((s.dossier / "commande.feature").read_text(encoding="utf-8") for s in (s1, s2))
    assert s1.dossier != s2.dossier
    assert '"Martin SARL" à "Lyon"' in t1 and '"Durand Industrie" à "Lyon"' in t2, "case vide du jeu : la ville de « Par défaut »"
    assert json.loads(_joues(base, e2))["jeu"] == "Grosse commande"


# ── 3. Une valeur qui manque : bloqué, jamais joué ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("feature, nommee", [
    (FEATURE.replace("{{ville}}", "{{pays}}"), "variable inconnue « pays »"),
    (FEATURE.replace("{{ville}}", "{{ville}"), "mal écrite"),
    (FEATURE, "variable sans valeur « ville »"),
])
def test_falsifiable_une_valeur_qui_manque_bloque_le_cas_sans_le_jouer(base, feature, nommee):
    pid, cid, vid, ids = _cas(base, feature, variables={"client": "Martin SARL", "ville": ""})
    eid = _execution(base, cid, vid)

    script = service.preparer_le_script(base, eid, cid, vid, "commande")

    assert script.dossier is None and nommee in script.blocage and "pas été joué" in script.blocage
    assert _joues(base, eid) == ""


def test_falsifiable_run_execution_ecrit_bloque_et_ne_lance_jamais_behave(base, monkeypatch):
    pid, cid, vid, _ = _cas(base, FEATURE.replace("{{ville}}", "{{pays}}"), variables={"client": "Martin SARL"})
    eid = _execution(base, cid, vid)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: get_initialized_db(config.DB_PATH))

    def interdit(**_kw):
        raise AssertionError("Behave ne doit pas être lancé : une donnée de test manque")
    monkeypatch.setattr(run_service, "BehaveRunner", interdit)

    run_service.run_execution(eid, "commande", cid, vid)

    ligne = base.execute("SELECT execution_status, functional_status, error_message FROM execution WHERE id=?", (eid,)).fetchone()
    assert (ligne[0], ligne[1]) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE)
    assert "variable inconnue « pays »" in ligne[2]
    assert st.statut_de_test(ligne[0], ligne[1], "") == st.STATUT_BLOCKED, "« bloqué » à l'écran, jamais « conforme » ni « à refaire »"
    cas = base.execute("SELECT last_execution_status FROM test_case WHERE id=?", (cid,)).fetchone()[0]
    assert cas == st.EXEC_BLOCKED


def test_run_execution_joue_la_copie_aux_valeurs_posees_et_ne_repare_pas(base, monkeypatch):
    pid, cid, vid, _ = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    eid = _execution(base, cid, vid)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: get_initialized_db(config.DB_PATH))
    recus = {}

    class Runner:
        connection = {}

        def __init__(self, **kw):
            recus.update(kw)

    monkeypatch.setattr(run_service, "BehaveRunner", Runner)
    monkeypatch.setattr(run_service, "resolve_connection", lambda *a: {})
    monkeypatch.setattr(run_service, "_execute_and_persist", lambda *a, **k: "verdict")
    reparations = []   # une exception levée ici serait avalée par le filet de la réparation : on COMPTE les appels
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **kw: reparations.append(kw))

    run_service.run_execution(eid, "commande", cid, vid)

    assert recus["generated_dir"] == config.DATA_DIR / "executions" / str(eid) / "script"
    assert reparations == [], "pas de réparation automatique d'un test joué avec des valeurs posées"


def test_un_projet_sans_variable_reste_repare_comme_avant(base, monkeypatch):
    """Contre-épreuve du test précédent : sans donnée de test, la réparation automatique est toujours tentée."""
    pid, cid, vid, _ = _cas(base, "Fonctionnalité: X\n  Scénario: Y\n    Alors la page affiche le texte \"ok\"\n")
    eid = _execution(base, cid, vid)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: get_initialized_db(config.DB_PATH))

    class Runner:
        connection = {}

        def __init__(self, **kw):
            assert "generated_dir" not in kw, "le fichier partagé d'aujourd'hui"
    monkeypatch.setattr(run_service, "BehaveRunner", Runner)
    monkeypatch.setattr(run_service, "resolve_connection", lambda *a: {})
    monkeypatch.setattr(run_service, "_execute_and_persist", lambda *a, **k: "verdict")
    reparations = []
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **kw: reparations.append(kw))

    run_service.run_execution(eid, "commande", cid, vid)

    assert len(reparations) == 1


# ── 4. Figées au lancement (A29) ──────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_les_valeurs_sont_figees_au_lancement_et_une_relance_les_reprend(base):
    pid, cid, vid, ids = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    depot = TestDataRepo(base)
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ids["client"]: "Autre client"})   # modifié APRÈS le lancement

    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))   # une relance
    eid = _execution(base, cid, vid, run_id)
    script = service.preparer_le_script(base, eid, cid, vid, "commande")

    assert '"Martin SARL"' in (script.dossier / "commande.feature").read_text(encoding="utf-8")
    figes = json.loads(RunRepo(base).get(run_id)["parametres_figes"])
    assert figes["valeurs"]["client"] == {"valeur": "Martin SARL", "origine": "Par défaut"}


def test_falsifiable_un_jeu_a_la_corbeille_empeche_le_lancement(base, monkeypatch):
    pid, cid, vid, ids = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    depot = TestDataRepo(base)
    export = depot.creer_jeu(pid, nom="Export")
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])
    base.execute("UPDATE test_run SET dataset_id=? WHERE id=?", (export, run_id))
    base.commit()
    depot.supprimer_jeu(pid, export, par="admin")
    monkeypatch.setattr("testpilot.connectors.runtime_env.verifier_connexion", lambda *a, **k: {})

    with pytest.raises(campaign_service.CampaignError) as refus:
        campaign_service.start_campaign(base, run_id)

    assert refus.value.code == "dataset_missing"
    assert RunRepo(base).get(run_id)["status"] != "running", "la campagne n'est pas passée « en cours »"


def test_un_projet_sans_variable_ne_fige_rien(base):
    pid, cid, vid, _ = _cas(base)
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])

    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))

    assert RunRepo(base).get(run_id)["parametres_figes"] == ""


def test_des_valeurs_figees_illisibles_bloquent_au_lieu_de_deviner(base):
    pid, cid, vid, _ = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])
    base.execute("UPDATE test_run SET parametres_figes='{pas du json' WHERE id=?", (run_id,))
    base.commit()

    script = service.preparer_le_script(base, _execution(base, cid, vid, run_id), cid, vid, "commande")

    assert script.dossier is None and "illisibles" in script.blocage


# ── Revue du 2026-10-14 ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_toutes_les_variables_a_la_corbeille_le_test_est_bloque_pas_joue_tel_quel(base):
    """Le raccourci « comme aujourd'hui » ne valait que pour zéro variable vivante : `{{client}}` était alors saisi tel quel
    dans l'application, et un vert restait possible (A31 : « bloqué »)."""
    pid, cid, vid, ids = _cas(base, variables={"client": "Martin SARL", "ville": "Lyon"})
    depot = TestDataRepo(base)
    for vid_variable in ids.values():
        depot.supprimer_variable(pid, vid_variable, par="admin")

    seul = service.preparer_le_script(base, _execution(base, cid, vid), cid, vid, "commande")
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    en_campagne = service.preparer_le_script(base, _execution(base, cid, vid, run_id), cid, vid, "commande")

    for script in (seul, en_campagne):
        assert script.dossier is None and "variable à la corbeille « client »" in script.blocage
    assert "créez une nouvelle exécution" in en_campagne.blocage and "relancez" in seul.blocage


def test_un_blocage_en_campagne_est_inscrit_au_registre_et_ne_prend_pas_le_premier_essai(base, monkeypatch):
    from testpilot.store.repositories import ResultRepo

    pid, cid, vid, _ = _cas(base, FEATURE.replace("{{ville}}", "{{pays}}"), variables={"client": "Martin SARL"})
    run_id = RunRepo(base).create(project_id=pid, name="Campagne", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, cid, vid, run_id)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: get_initialized_db(config.DB_PATH))

    run_service.run_execution(eid, "commande", cid, vid)

    lignes = base.execute("SELECT execution_id FROM test_result WHERE run_id=?", (run_id,)).fetchall()
    assert [l[0] for l in lignes] == [eid], "le blocage figure dans les résultats de la campagne"
    assert base.execute("SELECT trigger FROM execution WHERE id=?", (eid,)).fetchone()[0] == "rerun"
    assert ExecutionRepo(base).has_for_version(vid) is False, "le vrai premier essai sera compté comme tel"
    assert ResultRepo  # le registre est bien celui des résultats de campagne
