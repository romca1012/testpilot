"""Lot 3 du déploiement (2026-07-24) : **rendre exploitable un résultat non concluant**.

Le déploiement se fait en sachant que tous les verdicts ne seront pas concluants. Encore
faut-il pouvoir *instruire* un « erreur technique » ou un « refus silencieux » — pas seulement
le constater.

**Le défaut.** Chaque run était assemblé dans un dossier temporaire **détruit en sortie**
(`shutil.rmtree`) : la sortie du moteur, son JSON détaillé, le `.feature` et les steps
réellement joués **disparaissaient**. Le rapport, reconstruit depuis la base, suffit à lire un
verdict — jamais à comprendre pourquoi. Un testeur devant « erreur technique » n'avait rien à
ouvrir.

⚠️ Aucun de ces tests ne lance Behave ni ne touche une application : ils exercent l'archivage,
son exposition et ses refus.
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import run_service
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ACCESS_PASSWORD", "")
    return TestClient(app_mod.app)


def _execution(conn, *, artifacts_path: str = "") -> int:
    pid = ProjectRepo(conn).create(name="Recette", connector_type="odoo",
                                   base_url="http://x", database="db",
                                   username="qa", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="F", steps_content="")
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    if artifacts_path:
        ExecutionRepo(conn).set_artifacts_path(eid, artifacts_path)
    return eid


# ── 1. L'archivage, avant la destruction du dossier de run ────────────────────

def test_le_runner_archive_la_trace_avant_de_detruire_le_dossier(tmp_path, monkeypatch):
    """Le cœur du correctif : ce que le `rmtree` emportait est désormais recopié avant."""
    archives = tmp_path / "archives"
    runner = BehaveRunner(generated_dir=tmp_path / "generated",
                          steps_library_dir=tmp_path / "lib",
                          runtime_dir=tmp_path / "runtime")
    runner.cibler_artefacts(archives)

    # Un dossier de run comme le runner en fabrique un, puis l'archivage tel qu'il l'appelle.
    run_dir = tmp_path / "run"
    (run_dir / "steps").mkdir(parents=True)
    (run_dir / "result.json").write_text('{"scenarios": []}', encoding="utf-8")
    (run_dir / "demande.feature").write_text("Fonctionnalité: Demande", encoding="utf-8")
    (run_dir / "steps" / "demande_steps.py").write_text("# steps", encoding="utf-8")

    runner._archiver(run_dir, "demande", dry_run=False, journal="sortie du moteur")

    noms = {f.name for f in archives.iterdir()}
    assert "execution.log" in noms                 # ce que la machine a déroulé
    assert "execution.behave.json" in noms         # le détail par scénario
    assert "demande.feature" in noms               # le test TEL QU'IL A ÉTÉ JOUÉ
    assert "demande_steps.py" in noms
    assert (archives / "execution.log").read_text(encoding="utf-8") == "sortie du moteur"


def test_le_dry_run_et_le_run_reel_ne_s_ecrasent_pas(tmp_path):
    """Les deux passages ont chacun leur trace : la vérification préalable explique souvent
    l'échec du run réel, et la perdre reviendrait à n'en garder que la moitié."""
    archives = tmp_path / "a"
    runner = BehaveRunner()
    runner.cibler_artefacts(archives)
    run_dir = tmp_path / "run"
    (run_dir / "steps").mkdir(parents=True)

    runner._archiver(run_dir, "m", dry_run=True, journal="phase de vérification")
    runner._archiver(run_dir, "m", dry_run=False, journal="phase réelle")

    assert (archives / "dry-run.log").read_text(encoding="utf-8") == "phase de vérification"
    assert (archives / "execution.log").read_text(encoding="utf-8") == "phase réelle"


def test_sans_cible_designee_rien_n_est_archive(tmp_path):
    """Le comportement d'avant reste le défaut : la CLI et les tests n'archivent pas."""
    runner = BehaveRunner()  # aucune cible
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    runner._archiver(run_dir, "m", dry_run=False, journal="x")   # ne doit rien lever
    assert list(tmp_path.iterdir()) == [run_dir]


def test_un_echec_d_archivage_ne_fait_PAS_tomber_le_run(tmp_path, monkeypatch):
    """⚠️ Le filet ne doit pas casser ce qu'il protège.

    Une exécution réelle a créé des données dans l'application testée. La faire échouer parce
    qu'un disque est plein ou qu'un droit manque serait une régression bien pire que l'absence
    de trace.
    """
    runner = BehaveRunner()
    runner.cibler_artefacts(tmp_path / "interdit")
    monkeypatch.setattr("pathlib.Path.mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein")))
    run_dir = tmp_path / "run"
    runner._archiver(run_dir, "m", dry_run=False, journal="x")   # aucune exception ne sort


def test_la_trace_SURVIT_a_un_vrai_run_behave(tmp_path):
    """⚠️ **Le test qui compte** — les précédents appellent `_archiver` directement, ce qui prouve
    la logique et **pas** qu'elle est branchée.

    C'est l'angle mort qui a déjà coûté cher au projet (l'étape 3a : l'unitaire passait avec une
    réponse stubée, le réel n'avait rien à capter). Ici on lance **vraiment** le sous-processus
    Behave — en `--dry-run`, donc sans navigateur, sans application et sans dépense — et on
    vérifie que la trace existe **après** le `rmtree` qui détruisait tout.
    """
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "demo.feature").write_text(
        "# language: fr\nFonctionnalité: Démo\n  Scénario: rien\n    Soit je ne fais rien\n",
        encoding="utf-8")
    (generated / "demo_steps.py").write_text(
        "from behave import given\n\n@given('je ne fais rien')\ndef pas_grand_chose(context):\n"
        "    pass\n", encoding="utf-8")

    archives = tmp_path / "archives"
    runner = BehaveRunner(generated_dir=generated, steps_library_dir=tmp_path / "vide",
                          runtime_dir=tmp_path / "vide", dry_timeout=120)
    runner.cibler_artefacts(archives)

    runner.dry_run("demo")   # vrai `python -m behave --dry-run`

    assert archives.is_dir(), "le dossier temporaire a été détruit avec la trace"
    noms = {f.name for f in archives.iterdir()}
    assert "dry-run.log" in noms
    assert "dry-run.behave.json" in noms
    assert "demo.feature" in noms          # le test tel qu'il a été joué
    assert "demo_steps.py" in noms
    # Le journal porte bien la sortie du MOTEUR, pas une chaîne vide qui aurait tout aussi bien
    # « passé » : un fichier créé mais vide ne prouve rien.
    assert "USING RUNNER" in (archives / "dry-run.log").read_text(encoding="utf-8")


def test_chaque_execution_a_son_PROPRE_dossier(tmp_path, monkeypatch):
    """Le même runner sert les tentatives de réparation, chacune avec sa ligne d'exécution :
    une cible figée ferait écrire toutes les tentatives dans le dossier de la première."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert run_service.dossier_artefacts(7) != run_service.dossier_artefacts(8)
    assert run_service.dossier_artefacts(7).name == "7"


# ── 2. La trace est consultable ───────────────────────────────────────────────

def test_l_api_liste_la_trace_avec_des_libelles_METIER(client, tmp_path):
    """Un QA ne doit pas avoir à deviner ce qu'est `execution.behave.json` (§8 du brief)."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        dossier = tmp_path / "art"
        dossier.mkdir()
        (dossier / "execution.log").write_text("journal", encoding="utf-8")
        (dossier / "demande.feature").write_text("Fonctionnalité: X", encoding="utf-8")
        eid = _execution(conn, artifacts_path=str(dossier))
    finally:
        conn.close()

    corps = client.get(f"/api/executions/{eid}/artifacts").json()
    assert corps["available"] is True
    libelles = {f["name"]: f["label"] for f in corps["files"]}
    assert libelles["execution.log"] == "Journal de l'exécution réelle"
    assert libelles["demande.feature"] == "Le test tel qu'il a été joué"


def test_le_contenu_d_un_artefact_est_servi(client, tmp_path):
    conn = get_initialized_db(config.DB_PATH)
    try:
        dossier = tmp_path / "art"
        dossier.mkdir()
        (dossier / "execution.log").write_text("TimeoutError sur le champ « TVA »", encoding="utf-8")
        eid = _execution(conn, artifacts_path=str(dossier))
    finally:
        conn.close()

    r = client.get(f"/api/executions/{eid}/artifacts/execution.log")
    assert r.status_code == 200
    assert "TimeoutError" in r.text


def test_une_execution_ancienne_DIT_qu_aucune_trace_n_a_ete_gardee(client):
    """⚠️ Pas une liste vide : « aucun fichier » et « aucune trace conservée » ne veulent pas dire
    la même chose. Les confondre, c'est prendre une absence de signal pour un signal."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        eid = _execution(conn)   # aucune trace : le cas de toutes les exécutions d'avant
    finally:
        conn.close()

    corps = client.get(f"/api/executions/{eid}/artifacts").json()
    assert corps["available"] is False
    assert "antérieure" in corps["reason"]
    assert corps["files"] == []


def test_un_dossier_disparu_est_DISTINGUE_d_une_absence_d_archivage(client, tmp_path):
    """Base restaurée sans son répertoire de données : le message doit envoyer chercher là."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        eid = _execution(conn, artifacts_path=str(tmp_path / "parti-ailleurs"))
    finally:
        conn.close()

    corps = client.get(f"/api/executions/{eid}/artifacts").json()
    assert corps["available"] is False
    assert "introuvable" in corps["reason"]


def test_on_ne_peut_pas_sortir_du_dossier_de_l_execution(client, tmp_path):
    """⚠️ Le nom demandé vient de l'extérieur et n'est JAMAIS concaténé au chemin : on cherche
    une correspondance exacte dans le dossier. Sur un serveur partagé, un `.env` et une clé de
    chiffrement dorment à côté."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        dossier = tmp_path / "art"
        dossier.mkdir()
        (dossier / "execution.log").write_text("ok", encoding="utf-8")
        (tmp_path / "secret.txt").write_text("MOT DE PASSE", encoding="utf-8")
        eid = _execution(conn, artifacts_path=str(dossier))
    finally:
        conn.close()

    for tentative in ("../secret.txt", "..%2Fsecret.txt", "%2e%2e%2fsecret.txt"):
        r = client.get(f"/api/executions/{eid}/artifacts/{tentative}")
        assert r.status_code == 404, tentative
        assert "MOT DE PASSE" not in r.text


def test_la_trace_json_reste_du_json_lisible(client, tmp_path):
    """Le détail par scénario doit rester exploitable par un outil, pas seulement à l'œil."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        dossier = tmp_path / "art"
        dossier.mkdir()
        (dossier / "execution.behave.json").write_text(
            json.dumps({"scenarios": [{"name": "cas nominal", "status": "failed"}]}),
            encoding="utf-8")
        eid = _execution(conn, artifacts_path=str(dossier))
    finally:
        conn.close()

    r = client.get(f"/api/executions/{eid}/artifacts/execution.behave.json")
    assert json.loads(r.text)["scenarios"][0]["status"] == "failed"
