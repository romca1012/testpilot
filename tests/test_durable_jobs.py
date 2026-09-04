"""La réponse 202 ne doit plus dépendre uniquement de la mémoire du processus."""

from __future__ import annotations

from testpilot import config
from testpilot.guardrails import durable_jobs
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import BackgroundJobRepo, GenerationJobRepo


class FauxBackground:
    def __init__(self):
        self.appels = []

    def add_task(self, fn, *args, **kwargs):
        self.appels.append((fn, args, kwargs))


def _base(tmp_path, monkeypatch):
    chemin = tmp_path / "testpilot.db"
    monkeypatch.setattr(config, "DB_URL", "")
    monkeypatch.setattr(config, "DB_PATH", chemin)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return chemin


def test_submit_persiste_avant_de_programmer(tmp_path, monkeypatch):
    _base(tmp_path, monkeypatch)
    fond = FauxBackground()
    conn = get_initialized_db()
    try:
        durable_id = durable_jobs.submit(
            conn, fond, kind="execution", args=[12, "ventes", 3, 4],
            kwargs={"triggered_by": "alice"}, queue_label="execution:12")
        job = BackgroundJobRepo(conn).get(durable_id)
        brut = conn.execute(
            "SELECT payload FROM background_job WHERE id=?", (durable_id,)).fetchone()["payload"]
    finally:
        conn.close()

    assert job["status"] == "queued"
    assert job["payload"]["args"] == [12, "ventes", 3, 4]
    assert brut.startswith("enc:v1:")
    assert "alice" not in brut
    assert fond.appels == [(durable_jobs.run_job, (durable_id,), {})]


def test_run_job_ne_se_execute_quune_fois(tmp_path, monkeypatch):
    _base(tmp_path, monkeypatch)
    conn = get_initialized_db()
    try:
        repo = BackgroundJobRepo(conn)
        repo.creer("durable-1", kind="generation", queue_label="g:1",
                   payload={"args": ["metier-1"], "kwargs": {"module_id": 2}})
    finally:
        conn.close()

    appels = []
    monkeypatch.setattr(durable_jobs, "_call", lambda kind, args, kwargs: appels.append(
        (kind, args, kwargs)))
    durable_jobs.run_job("durable-1")
    durable_jobs.run_job("durable-1")

    conn = get_initialized_db()
    try:
        assert BackgroundJobRepo(conn).get("durable-1")["status"] == "completed"
    finally:
        conn.close()
    assert appels == [("generation", ["metier-1"], {"module_id": 2})]


def test_redemarrage_clot_un_actif_sans_le_rejouer(tmp_path, monkeypatch):
    _base(tmp_path, monkeypatch)
    conn = get_initialized_db()
    try:
        GenerationJobRepo(conn).creer("generation-1", module_id=7, payload={})
        repo = BackgroundJobRepo(conn)
        repo.creer("durable-2", kind="generation", queue_label="g:2",
                   payload={"args": ["generation-1"], "kwargs": {}})
        assert repo.claim("durable-2")
    finally:
        conn.close()

    assert durable_jobs.recover_at_startup() == 0

    conn = get_initialized_db()
    try:
        durable = BackgroundJobRepo(conn).get("durable-2")
        generation = GenerationJobRepo(conn).get("generation-1")
    finally:
        conn.close()
    assert durable["status"] == "failed"
    assert generation["status"] == "failed"
    assert "redémarrage" in generation["error"]


def test_purge_ne_touche_jamais_un_job_en_attente(tmp_path, monkeypatch):
    _base(tmp_path, monkeypatch)
    conn = get_initialized_db()
    try:
        repo = BackgroundJobRepo(conn)
        repo.creer("termine", kind="generation", queue_label="a",
                   payload={"args": [], "kwargs": {}})
        assert repo.claim("termine")
        repo.terminer("termine")
        conn.execute("UPDATE background_job SET finished_at='2020-01-01T00:00:00+00:00'"
                     " WHERE id='termine'")
        repo.creer("attente", kind="generation", queue_label="b",
                   payload={"args": [], "kwargs": {}})
        assert repo.purger_termines("2021-01-01T00:00:00+00:00") == 1
        assert repo.get("termine") is None
        assert repo.get("attente")["status"] == "queued"
    finally:
        conn.close()


def test_redemarrage_reprogramme_un_job_qui_navait_pas_commence(tmp_path, monkeypatch):
    _base(tmp_path, monkeypatch)
    conn = get_initialized_db()
    try:
        BackgroundJobRepo(conn).creer(
            "a-reprendre", kind="generation", queue_label="g:reprise",
            payload={"args": ["generation-2"], "kwargs": {}},
        )
    finally:
        conn.close()

    demarres = []

    class FauxThread:
        def __init__(self, *, target, args, daemon, name):
            self.target, self.args, self.daemon, self.name = target, args, daemon, name

        def start(self):
            demarres.append((self.target, self.args, self.daemon, self.name))

    monkeypatch.setattr(durable_jobs.threading, "Thread", FauxThread)
    assert durable_jobs.recover_at_startup() == 1
    assert demarres == [(durable_jobs.run_job, ("a-reprendre",), True,
                         "testpilot-job-a-repren")]
