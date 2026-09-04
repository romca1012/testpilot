"""Preuves du runtime PostgreSQL réel.

Ces tests sont opt-in afin que la suite locale SQLite reste autonome. La CI de production doit
fournir ``TESTPILOT_TEST_POSTGRES_URL`` vers une base jetable déjà migrée par Alembic.
"""

from __future__ import annotations

import os
import shutil
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api.app import app
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    BackgroundJobRepo,
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ResultRepo,
    RunRepo,
    SettingRepo,
    UserRepo,
    VersionRepo,
)


def test_file_durable_reclame_atomiquement_un_job_sur_postgresql(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    job_id = f"durable-{uuid4().hex}"
    conn = get_initialized_db()
    try:
        repo = BackgroundJobRepo(conn)
        repo.creer(job_id, kind="execution", queue_label=job_id,
                   payload={"args": [1], "kwargs": {}})
        assert repo.claim(job_id) is True
        assert repo.claim(job_id) is False
        repo.terminer(job_id)
        assert repo.get(job_id)["status"] == "completed"
    finally:
        conn.close()

URL = os.getenv("TESTPILOT_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="PostgreSQL de test non configuré")


@pytest.fixture(autouse=True)
def postgres(monkeypatch):
    monkeypatch.setattr(config, "DB_URL", URL)


def test_repositories_crud_sur_postgresql():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet PG {suffixe}", connector_type="odoo",
                                       connector_version="19")
        mid = ModuleRepo(conn).create(project_id=pid, name="Facturation")
        cid = CaseRepo(conn).create_manual(module_id=mid, title="Créer une facture",
                                           test_steps='["ouvrir"]', expected_result="créée")
        case = CaseRepo(conn).get(cid)
        assert case["project_id"] == pid
        assert ProjectRepo(conn).get(pid)["connector_version"] == "19"
        assert VersionRepo(conn).get(case["current_version_id"])["title"] == "Créer une facture"
    finally:
        conn.close()


def test_api_utilise_postgresql_de_bout_en_bout(tmp_path, monkeypatch):
    # `DATA_DIR` isolé : la connexion passe par PostgreSQL (fixture `postgres` ci-dessus), mais
    # `access.creer_jeton` (session du login réel plus bas) crée sa clé de signature sous
    # `config.DATA_DIR` quel que soit le moteur de base — sans isolation, elle atterrit dans le
    # VRAI `data/` du poste (trouvé en CI, garde-fou `conftest.py`).
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        UserRepo(conn).create(username=f"admin-{suffixe}",
                              password_hash=access.hacher_mot_de_passe("motdepasse"),
                              role=access.ROLE_ADMIN)
    finally:
        conn.close()

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={
            "username": f"admin-{suffixe}", "password": "motdepasse",
        })
        assert login.status_code == 200, login.text
        creation = client.post("/api/projects", json={
            "name": f"API PG {suffixe}", "connector_type": "odoo",
            "connector_version": "17", "base_url": "http://odoo.test",
        })
        assert creation.status_code == 201, creation.text
        assert creation.json()["connector_version"] == "17"
        assert any(p["id"] == creation.json()["id"] for p in client.get("/api/projects").json())


def test_postgresql_refuse_un_doublon_de_nom_independant_de_la_casse():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        repo = ProjectRepo(conn)
        repo.create(name=f"Projet Casse {suffixe}")
        with pytest.raises(psycopg.IntegrityError):
            conn.execute(
                "INSERT INTO project (name, created_at) VALUES (?,?)",
                (f"PROJET CASSE {suffixe}", "2026-08-28T00:00:00+00:00"),
            )
        conn.rollback()
    finally:
        conn.close()


def test_ajouter_un_resultat_de_scenario_renvoie_un_id_valide_sur_postgresql():
    """Trouvé en pratique (2026-09-03) : `scenario_result` manquait de `_TABLES_AVEC_ID`
    (portable_connection.py) — `ExecutionRepo.add_scenario_result`, appelée à CHAQUE scénario
    Behave exécuté, aurait levé `TypeError: int() argument must be... not 'NoneType'` au tout
    premier run réel contre PostgreSQL. Preuve comportementale, pas seulement statique (voir
    `tests/test_tables_avec_id_postgres.py` pour le garde-fou qui empêche la régression)."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet scénario {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module scénario")
        cid = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas scénario", test_steps='["agir"]', expected_result="ok")
        case = CaseRepo(conn).get(cid)
        execution_repo = ExecutionRepo(conn)
        eid = execution_repo.create(test_case_id=cid, version_id=case["current_version_id"])

        rid = execution_repo.add_scenario_result(
            execution_id=eid, scenario_name="Scénario nominal",
            execution_status="success", functional_status="conforme")

        assert isinstance(rid, int) and rid > 0
        resultats = execution_repo.list_scenario_results(eid)
        assert [r["id"] for r in resultats] == [rid]
        assert resultats[0]["scenario_name"] == "Scénario nominal"
    finally:
        conn.close()


def test_insert_or_ignore_se_traduit_correctement_en_on_conflict_do_nothing():
    """Seul site du dépôt utilisant `INSERT OR IGNORE` (`RunRepo.create`, liaison
    `test_run_case`) — traduit en `ON CONFLICT DO NOTHING` par `portable_connection._adapter_sql`.
    Preuve que la déduplication marche VRAIMENT sous PostgreSQL, pas seulement que la requête ne
    lève pas d'erreur de syntaxe : un `case_id` en double dans la sélection ne doit produire
    qu'UNE seule ligne de liaison, comme sous SQLite."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet run {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module run")
        cid = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas run", test_steps='["agir"]', expected_result="ok")

        run_id = RunRepo(conn).create(
            project_id=pid, name=f"Run {suffixe}", selection_mode="frozen",
            case_ids=[cid, cid, cid])  # le même cas 3 fois : la dédup doit tenir

        liaisons = conn.execute(
            "SELECT case_id FROM test_run_case WHERE run_id=?", (run_id,)).fetchall()
        assert [r["case_id"] for r in liaisons] == [cid]
    finally:
        conn.close()


def test_upsert_on_conflict_do_update_reecrit_la_valeur_existante():
    """`ON CONFLICT(...) DO UPDATE SET col=excluded.col` (`SettingRepo.ecrire`,
    `ProjectAccessRepo`/`ProjectMemberRepo`/`ProjectGroupAccessRepo`.set — 4 sites au total) est
    du SQL standard, identique sous SQLite et PostgreSQL : `_adapter_sql` ne le traduit pas
    spécialement (seuls `?`→`%s` s'appliquent). Preuve que ça marche vraiment, pas seulement que
    la requête ne lève pas d'erreur de syntaxe : une deuxième écriture sur la MÊME clé doit
    REMPLACER la valeur, jamais dupliquer la ligne."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        # `SettingRepo` a un vocabulaire FERMÉ (`CLES_CONNUES`) — une clé arbitraire est refusée
        # avant même d'atteindre le SQL. `reference_url_template` est une clé réelle et neutre.
        cle = "reference_url_template"
        repo = SettingRepo(conn)
        repo.ecrire(cle, f"première valeur {suffixe}", par="qa")
        repo.ecrire(cle, f"valeur écrasée {suffixe}", par="qa")

        lignes = conn.execute(
            "SELECT value FROM app_setting WHERE key=?", (cle,)).fetchall()
        assert [r["value"] for r in lignes] == [f"valeur écrasée {suffixe}"]
    finally:
        conn.close()


def test_flux_metier_complet_dune_campagne_sur_postgresql():
    """LE test qui manquait : les 7 tests au-dessus prouvent chaque traduction SQL isolément, mais
    aucun ne rejoue le flux RÉEL d'un utilisateur — créer un projet, un module, plusieurs cas, une
    campagne qui les regroupe, les jouer, enregistrer leurs résultats — de bout en bout contre un
    VRAI PostgreSQL. Inspiré de `tests/test_run_campagne.py`
    (`test_cases_avec_resultats_rattache_l_execution_DU_run`,
    `test_un_cas_sans_execution_dans_le_run_est_non_teste`) et de `tests/test_resultat_du_dernier.py`
    — mêmes assertions que sous SQLite, rejouées ici pour prouver qu'elles tiennent aussi sous
    PostgreSQL (types, séquences, `INSERT OR IGNORE` → `ON CONFLICT`, triggers d'invariants...).
    """
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        # 1. Un projet, un module, TROIS cas — la campagne doit rester TRANSVERSE (elle ne
        #    contraint aucun module particulier, `0022` n°8).
        pid = ProjectRepo(conn).create(name=f"Projet flux {suffixe}", connector_type="odoo",
                                       connector_version="19")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module flux")
        case_repo = CaseRepo(conn)
        c1 = case_repo.create_manual(module_id=mid, title="Cas conforme",
                                     test_steps='["agir"]', expected_result="ok")
        c2 = case_repo.create_manual(module_id=mid, title="Cas en échec",
                                     test_steps='["agir"]', expected_result="ok")
        c3 = case_repo.create_manual(module_id=mid, title="Cas jamais joué",
                                     test_steps='["agir"]', expected_result="ok")

        # 2. La campagne REGROUPE les trois cas, figés (`frozen`) — elle NAÎT en brouillon, rien
        #    n'est encore joué (`0022` 8.c.1).
        run_repo = RunRepo(conn)
        rid = run_repo.create(project_id=pid, name=f"Campagne {suffixe}",
                              selection_mode="frozen", case_ids=[c1, c2, c3])
        assert run_repo.get(rid)["status"] == "draft"
        assert run_repo.case_ids(rid) == sorted([c1, c2, c3])

        # 3. La campagne se LANCE : deux cas sont joués (l'un réussit, l'autre échoue
        #    fonctionnellement), le troisième reste NON TESTÉ — un échec n'arrête jamais la
        #    campagne (`test_un_cas_en_echec_n_arrete_pas_la_campagne`, SQLite).
        run_repo.set_status(rid, "running", launched=True)
        execution_repo = ExecutionRepo(conn)

        def _jouer(case_id: int, *, execution_status: str, functional_status: str) -> int:
            case = case_repo.get(case_id)
            eid = execution_repo.create(test_case_id=case_id,
                                        version_id=case["current_version_id"])
            conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
            conn.commit()
            execution_repo.finalize(
                eid, execution_status=execution_status, functional_status=functional_status,
                scenarios_total=1, scenarios_passed=1 if execution_status == "success" else 0,
                scenarios_failed=0 if execution_status == "success" else 1,
                cost_usd=0.0, iterations=0, duration_seconds=1.0)
            case_repo.update_last_outcome(
                case_id, execution_status=execution_status, functional_status=functional_status,
                executed_at="2026-09-03T10:00:00+00:00")
            return eid

        eid1 = _jouer(c1, execution_status="success", functional_status="conforme")
        eid2 = _jouer(c2, execution_status="success", functional_status="non_conforme")
        run_repo.set_status(rid, "completed", completed=True)

        # 4. État final — EXACTEMENT ce qu'un test SQLite équivalent vérifierait (comptages via le
        #    registre, pas une valeur déclarée) :
        run = run_repo.get(rid)
        assert run["status"] == "completed"

        resume = run_repo.list_for_project(pid)
        ligne = next(r for r in resume if r["id"] == rid)
        assert ligne["frozen_count"] == 3, "les trois cas restent membres de la campagne"
        assert ligne["tested_count"] == 2, "seuls les deux cas JOUÉS comptent comme testés"

        cases = {c["id"]: c for c in run_repo.cases_with_results(rid)}
        assert cases[c1]["result"]["execution_status"] == "success"
        assert cases[c1]["result"]["functional_status"] == "conforme"
        assert cases[c2]["result"]["execution_status"] == "success"
        assert cases[c2]["result"]["functional_status"] == "non_conforme"
        assert cases[c3]["result"] is None, "le troisième cas n'a jamais été joué"

        derniers = ResultRepo(conn).derniers_du_run(rid)
        assert set(derniers) == {c1, c2}
        assert derniers[c1]["execution_id"] == eid1
        assert derniers[c2]["execution_id"] == eid2

        # 5. Un cas SUPPRIMÉ quitte la campagne sans l'emporter (`test_un_cas_inclus_dans_un_run...`,
        #    SQLite) — la cascade `test_run_case` doit tenir sous PostgreSQL aussi.
        case_repo.delete(c3)
        assert run_repo.case_ids(rid) == sorted([c1, c2]), "le cas supprimé quitte la campagne"
        assert run_repo.get(rid) is not None, "la campagne survit, avec ses autres cas"
    finally:
        conn.close()


def test_postgresql_refuse_un_resultat_dont_le_mode_contredit_la_campagne():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet mode {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module mode")
        case_id = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas mode", test_steps='["agir"]', expected_result="ok")
        curseur = conn.execute(
            "INSERT INTO test_run (project_id, name, description, refs, selection_mode, mode,"
            " status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, "Run manuel", "", "", "frozen", "manuelle", "draft",
             "2026-08-28T00:00:00+00:00"),
        )
        run_id = curseur.lastrowid
        with pytest.raises(psycopg.IntegrityError, match="ne concorde pas"):
            conn.execute(
                "INSERT INTO test_result (case_id, run_id, mode, statut_manuel, created_at, created_by)"
                " VALUES (?,?,?,?,?,?)",
                (case_id, run_id, "automatique", "passed", "2026-08-28T00:00:00+00:00", "audit"),
            )
        conn.rollback()
    finally:
        conn.close()


def test_cycle_sauvegarde_puis_restauration_complet_sur_postgresql(tmp_path):
    """Miroir PostgreSQL de `tests/test_sauvegarde_restauration.py`
    (`test_cycle_sauvegarde_puis_restauration_complet`) : une VRAIE base, de VRAIES données
    écrites par les dépôts existants (pas du SQL à la main), sauvegarde par
    `scripts.sauvegarder_postgresql` (`pg_dump`), PERTE RÉELLE du contenu — le schéma entier est
    rasé, l'équivalent PostgreSQL de supprimer le fichier unique d'une base SQLite —, restauration
    (`pg_restore --clean`), puis comparaison des données via les MÊMES dépôts. Pas seulement
    « la commande a réussi », la preuve qu'une sauvegarde PostgreSQL restaure VRAIMENT.

    ⚠️ Ignoré si `pg_dump`/`pg_restore` sont absents du PATH (ou de
    `TESTPILOT_PG_DUMP_BIN`/`TESTPILOT_PG_RESTORE_BIN`) — exactement le cas que le script doit
    détecter proprement (`_verifier_outil`), pas un manque de cette preuve.
    """
    from scripts.sauvegarder_postgresql import PG_DUMP_BIN, PG_RESTORE_BIN, restaurer, sauvegarder

    if shutil.which(PG_DUMP_BIN) is None or shutil.which(PG_RESTORE_BIN) is None:
        pytest.skip("pg_dump/pg_restore non installés sur cette machine")

    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet sauvegarde PG {suffixe}",
                                       description="cycle sauvegarde postgresql")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module sauvegarde")
        cid = CaseRepo(conn).create_manual(module_id=mid, title="Cas à restaurer",
                                           test_steps='["agir"]', expected_result="ok")
    finally:
        conn.close()

    # 1. Sauvegarde — la base porte réellement les données ci-dessus.
    dossier_sauvegardes = tmp_path / "sauvegardes_pg"
    fichier_sauvegarde = sauvegarder(dossier=dossier_sauvegardes, garder=10)
    assert fichier_sauvegarde.exists()
    assert fichier_sauvegarde.stat().st_size > 0

    # 2. PERTE réelle : le schéma entier est rasé (`DROP SCHEMA ... CASCADE`), pas seulement une
    #    table vidée — la connexion directe, hors des repositories, le prouve : même la lecture la
    #    plus simple échoue.
    dsn = config.DB_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    conn_brut = psycopg.connect(dsn)
    try:
        conn_brut.execute("DROP SCHEMA public CASCADE")
        conn_brut.execute("CREATE SCHEMA public")
        conn_brut.commit()
    finally:
        conn_brut.close()

    conn_verif = psycopg.connect(dsn)
    try:
        with pytest.raises(psycopg.errors.UndefinedTable):
            conn_verif.execute("SELECT * FROM project").fetchall()
    finally:
        conn_verif.rollback()
        conn_verif.close()

    # 3. Restauration depuis la sauvegarde.
    dbname = restaurer(fichier_sauvegarde)
    assert dbname

    # 4. Les données sont IDENTIQUES — comparées via les mêmes dépôts, pas juste « ça n'a pas
    #    planté ». Le schéma applicatif (Alembic compris) est aussi revenu : `get_initialized_db`
    #    reconnecte sans erreur.
    conn2 = get_initialized_db()
    try:
        projet = ProjectRepo(conn2).get(pid)
        assert projet is not None
        assert projet["name"] == f"Projet sauvegarde PG {suffixe}"

        module = ModuleRepo(conn2).get(mid)
        assert module is not None
        assert module["name"] == "Module sauvegarde"

        cas = CaseRepo(conn2).get(cid)
        assert cas is not None
        assert cas["title"] == "Cas à restaurer"
    finally:
        conn2.close()
