"""Flux SSE `GET /api/projects/{id}/events` — audit 2026-09-07, « vrai temps réel ».

Le générateur (`routes.projects._flux_evenements`) est piloté directement en asyncio, sans passer
par une vraie connexion HTTP en flux : le client de test (`starlette.testclient`) collecte le
corps entier avant de le rendre, ce qui bloquerait indéfiniment sur un flux volontairement sans
fin. La logique de routage par projet (isolation, file pleine…) est couverte séparément par
`test_events_bus.py`, plus rapide et déterministe.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.routes.projects import _flux_evenements
from testpilot.api.services import events_bus


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "sse.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


class _RequeteFactice:
    """Reste « connectée » jusqu'à ce que le test décide sinon — un vrai `Request` FastAPI
    répondrait pareil tant que le socket TCP du navigateur reste ouvert."""

    def __init__(self):
        self.deconnectee = False

    async def is_disconnected(self) -> bool:
        return self.deconnectee


def test_le_flux_relaie_un_evenement_publie_pendant_la_connexion():
    async def scenario():
        requete = _RequeteFactice()
        gen = _flux_evenements(project_id=1, request=requete)
        premiere_ligne = await gen.__anext__()
        assert premiere_ligne == "retry: 3000\n\n"
        assert events_bus.nombre_abonnes(1) == 1, "l'abonnement doit exister dès la 1ère ligne"

        events_bus.publier(1, {"kind": "case_metier_changed", "case_id": 7})
        ligne = await gen.__anext__()
        assert ligne == 'data: {"kind": "case_metier_changed", "case_id": 7}\n\n'

        requete.deconnectee = True
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        assert events_bus.nombre_abonnes(1) == 0, "la déconnexion doit désabonner proprement"

    asyncio.run(scenario())


def test_un_evenement_d_un_AUTRE_projet_n_arrive_jamais_sur_ce_flux():
    async def scenario():
        requete = _RequeteFactice()
        gen = _flux_evenements(project_id=1, request=requete)
        await gen.__anext__()   # "retry: 3000\n\n"

        events_bus.publier(2, {"kind": "case_metier_changed", "case_id": 7})   # AUTRE projet
        events_bus.publier(1, {"kind": "case_created", "case_id": 9})         # CE projet

        ligne = await gen.__anext__()
        assert json.loads(ligne[len("data: "):]) == {"kind": "case_created", "case_id": 9}

        requete.deconnectee = True
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    asyncio.run(scenario())


def test_editer_un_cas_publie_bien_un_evenement_pour_son_projet(client):
    """Bout en bout côté PUBLICATION (pas le flux HTTP, voir le docstring du module) : la route
    d'édition doit vraiment appeler `events_bus.publier` avec le bon projet."""
    pid = client.post("/api/projects", json={
        "name": "P", "base_url": "http://x", "database": "db",
        "username": "u", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    case = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas", "test_steps": ["Une étape"], "expected_result": "Un résultat"}).json()

    q = events_bus.abonner(pid)
    try:
        r = client.patch(f"/api/cases/{case['id']}/metier", json={"preconditions": "x"})
        assert r.status_code == 200
        assert q.get(timeout=1) == {"kind": "case_metier_changed", "case_id": case["id"]}
    finally:
        events_bus.desabonner(pid, q)


def test_un_compte_sans_acces_au_projet_ne_peut_pas_ecouter_ses_evenements(client):
    """Même fermeture par défaut que le reste de l'API (audit 2026-09-07) : écouter un projet
    n'est pas un geste distinct de le lire."""
    r = client.get("/api/projects/999999/events")
    assert r.status_code == 404
