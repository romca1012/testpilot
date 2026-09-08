"""GenerationJobRepo — le job de génération PERSISTÉ (migration 29, 2026-08-07).

Ce que ces tests figent :
- créer/lire/mettre à jour un job survit à une nouvelle connexion (donc à un redémarrage) ;
- `maj()` route les clés connues vers leurs colonnes, le reste dans `payload`, sans rien perdre ;
- un job "running" resté sans nouvelle trop longtemps est réputé mort, et cette conclusion
  s'ÉCRIT (pas seulement renvoyée une fois) ;
- un job "running" récent n'est PAS touché — un multiple large du délai réel de génération.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from testpilot import config
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import GenerationJobRepo, ModuleRepo, ProjectRepo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "jobs.db")
    yield c
    c.close()


def _module(conn) -> int:
    pid = ProjectRepo(conn).create(name="Portail")
    return ModuleRepo(conn).create(project_id=pid, name="Demandes")


def test_creer_puis_get_rend_le_job_a_plat(conn):
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid, payload={"title": "T", "spec_content": "S"})

    job = repo.get("job1")

    assert job["status"] == "running"
    assert job["module_id"] == mid
    assert job["case_ids"] == []
    assert job["title"] == "T"
    assert job["spec_content"] == "S"


def test_get_d_un_job_INEXISTANT_rend_None(conn):
    assert GenerationJobRepo(conn).get("fantome") is None


def test_maj_route_les_colonnes_connues_ET_garde_le_reste_dans_payload(conn):
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid, payload={"title": "T"})

    repo.maj("job1", status="awaiting_metier", cases=[{"title": "Cas A"}], cost_usd=0.05)

    job = repo.get("job1")
    assert job["status"] == "awaiting_metier"
    assert job["cost_usd"] == 0.05
    assert job["cases"] == [{"title": "Cas A"}]
    assert job["title"] == "T"   # rien perdu du payload précédent


def test_maj_case_ids_est_bien_persiste_en_JSON(conn):
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid)

    repo.maj("job1", status="done", case_ids=[10, 11, 12])

    assert GenerationJobRepo(conn).get("job1")["case_ids"] == [10, 11, 12]


def test_survit_a_une_NOUVELLE_connexion(conn, tmp_path, monkeypatch):
    """Le cœur du correctif : ce que `_JOBS` (un dict Python) ne pouvait pas faire."""
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    mid = _module(conn)
    GenerationJobRepo(conn).creer("job1", module_id=mid, payload={"title": "Persistant"})
    conn.close()

    reconnecte = get_initialized_db(tmp_path / "jobs.db")
    try:
        job = GenerationJobRepo(reconnecte).get("job1")
        assert job is not None
        assert job["title"] == "Persistant"
    finally:
        reconnecte.close()


def test_maj_d_un_job_INEXISTANT_leve_une_erreur_claire(conn):
    with pytest.raises(ValueError, match="introuvable"):
        GenerationJobRepo(conn).maj("fantome", status="done")


# ── Détection de blocage (serveur redémarré en plein milieu) ──────────────────

def _vieillir(conn, job_id: str, il_y_a_secondes: int) -> None:
    """Triche l'horloge d'un job pour simuler un job abandonné depuis longtemps — sans dépendre
    d'un vrai sommeil dans le test."""
    passe = (datetime.now(timezone.utc) - timedelta(seconds=il_y_a_secondes)).isoformat()
    conn.execute("UPDATE generation_job SET updated_at=? WHERE id=?", (passe, job_id))
    conn.commit()


def test_un_job_RUNNING_bloque_depuis_longtemps_devient_FAILED_a_la_lecture(conn):
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid)
    _vieillir(conn, "job1", GenerationJobRepo.SEUIL_BLOQUE_SECONDES + 60)

    job = repo.get("job1")

    assert job["status"] == "failed"
    assert "redémarré" in job["error"]


def test_la_conclusion_de_blocage_est_ECRITE_pas_seulement_renvoyee_une_fois(conn):
    """Deux lectures indépendantes (deux requêtes HTTP, par exemple) doivent voir la MÊME
    vérité — pas juste celle qui a eu la chance d'arriver en premier."""
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid)
    _vieillir(conn, "job1", GenerationJobRepo.SEUIL_BLOQUE_SECONDES + 60)
    repo.get("job1")   # première lecture : déclenche l'écriture

    ligne = conn.execute("SELECT status, error FROM generation_job WHERE id=?",
                         ("job1",)).fetchone()
    assert ligne["status"] == "failed"
    assert ligne["error"]


def test_un_job_RUNNING_recent_n_est_PAS_touche(conn):
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid)
    _vieillir(conn, "job1", 30)   # 30 secondes — normal pour une génération en cours

    job = repo.get("job1")

    assert job["status"] == "running"
    assert job["error"] == ""


def test_un_job_AWAITING_METIER_ancien_n_est_PAS_touche(conn):
    """Attendre une validation humaine pendant des heures est LÉGITIME — rien à voir avec un
    serveur mort, donc pas de repli ici."""
    mid = _module(conn)
    repo = GenerationJobRepo(conn)
    repo.creer("job1", module_id=mid)
    repo.maj("job1", status="awaiting_metier", cases=[])
    _vieillir(conn, "job1", GenerationJobRepo.SEUIL_BLOQUE_SECONDES + 3600)

    job = repo.get("job1")

    assert job["status"] == "awaiting_metier"
