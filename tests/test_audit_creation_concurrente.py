"""Une création concurrente ne doit pas remplacer le projet renvoyé au créateur."""

from testpilot.api import schemas
from testpilot.api.routes.projects import create_project
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


def test_creation_renvoie_son_identifiant_meme_si_un_autre_projet_arrive(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "audit.db")
    original = ProjectRepo.create

    def intercaler(self, **kwargs):
        identifiant = original(self, **kwargs)
        original(self, name="Projet créé entre insertion et réponse")
        return identifiant

    monkeypatch.setattr(ProjectRepo, "create", intercaler)
    try:
        resultat = create_project(schemas.ProjectIn(name="Équipe A"), conn=conn)
        assert resultat.name == "Équipe A"
        assert resultat.id != conn.execute("SELECT MAX(id) AS m FROM project").fetchone()["m"]
    finally:
        conn.close()
