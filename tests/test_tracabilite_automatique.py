"""§A du plan « fiabiliser le verdict automatique » (2026-08-06) : un résultat automatique doit
recevoir, comme un résultat manuel, un commentaire ET une preuve visuelle — pour TOUS les statuts.

Ce fichier exerce `run_service._persist` de bout en bout : le commentaire est écrit à la
CRÉATION de la ligne du registre (jamais par une UPDATE, cf. `ResultRepo` §7), et les captures
d'écran archivées par le runner sont rattachées comme des pièces jointes ordinaires.
"""
from __future__ import annotations

from testpilot.api.services import run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ResultRepo,
    RunRepo,
    VersionRepo,
)
from testpilot.verdict.status import CaseVerdict, ScenarioVerdict

import pytest


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "tracabilite.db")
    yield c
    c.close()


@pytest.fixture
def campagne(conn, tmp_path, monkeypatch):
    """Un projet, un cas, une campagne automatique — et `DATA_DIR` isolé (les captures et les
    pièces jointes en dépendent TOUTES LES DEUX)."""
    monkeypatch.setattr(run_service.config, "DATA_DIR", tmp_path)
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="# f", steps_content="# s")
    rid = RunRepo(conn).create(project_id=pid, name="Recette auto", case_ids=[cid])
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    conn.commit()
    return {"cas": cid, "run": rid, "execution": eid}


class _OutcomeVide:
    """`_persist` ne lit `outcome` QUE pour `real_run` (replis de champ, diagnostic de
    réparation) — un outcome sans run réel suffit à exercer le commentaire/captures."""
    real_run = None


def _verdict_passed() -> CaseVerdict:
    return CaseVerdict(execution_status="success", functional_status="conforme",
                       scenarios=[ScenarioVerdict("Scénario nominal", "success", "conforme")],
                       scenarios_passed=1, scenarios_failed=0)


def test_le_commentaire_est_ecrit_a_la_creation_du_resultat(conn, campagne, monkeypatch):
    monkeypatch.setattr(run_service.explication, "propose_explication",
                        lambda verdict, **k: ("Le formulaire a créé le ticket attendu.", 0.0173))

    run_service._persist(conn, campagne["execution"], campagne["cas"], _verdict_passed(),
                         _OutcomeVide(), 1.2, "nominal")

    resultat = ResultRepo(conn).dernier(campagne["run"], campagne["cas"])
    assert resultat is not None
    assert resultat["comment"] == "Le formulaire a créé le ticket attendu."
    assert resultat["mode"] == "automatique"


def test_le_cout_du_commentaire_est_trace_sous_sa_propre_phase_hors_budget_9(conn, campagne,
                                                                             monkeypatch):
    """Décision du porteur : la phase `"explication"` est tracée pour la visibilité, mais ne doit
    JAMAIS gonfler `creation_cost_usd` (le budget §9, qui ne mesure que analysis+generation)."""
    monkeypatch.setattr(run_service.explication, "propose_explication",
                        lambda verdict, **k: ("ok", 0.0173))

    run_service._persist(conn, campagne["execution"], campagne["cas"], _verdict_passed(),
                         _OutcomeVide(), 1.2, "nominal")

    costs = CostRepo(conn)
    assert costs.total_for_case_usd(campagne["cas"]) == pytest.approx(0.0173)
    assert costs.creation_cost_usd(campagne["cas"]) == 0.0   # §9 intact


def test_un_commentaire_vide_n_ecrit_aucun_cout(conn, campagne, monkeypatch):
    """`propose_explication` best-effort rend `("", 0.0)` sur un échec IA — rien à journaliser."""
    monkeypatch.setattr(run_service.explication, "propose_explication",
                        lambda verdict, **k: ("", 0.0))

    run_service._persist(conn, campagne["execution"], campagne["cas"], _verdict_passed(),
                         _OutcomeVide(), 1.2, "nominal")

    assert CostRepo(conn).total_for_case_usd(campagne["cas"]) == 0.0


def test_les_captures_archivees_sont_rattachees_comme_des_pieces_jointes(conn, campagne,
                                                                          monkeypatch):
    monkeypatch.setattr(run_service.explication, "propose_explication",
                        lambda verdict, **k: ("", 0.0))
    dossier_captures = run_service.dossier_artefacts(campagne["execution"]) / "screenshots"
    dossier_captures.mkdir(parents=True)
    (dossier_captures / "01-passed.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (dossier_captures / "02-passed.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)

    run_service._persist(conn, campagne["execution"], campagne["cas"], _verdict_passed(),
                         _OutcomeVide(), 1.2, "nominal")

    resultat = ResultRepo(conn).dernier(campagne["run"], campagne["cas"])
    pieces = ResultRepo(conn).pieces_jointes(resultat["id"])
    assert len(pieces) == 2
    assert all(p["content_type"] == "image/png" for p in pieces)
    # Le fichier existe VRAIMENT là où la pièce jointe prétend qu'il est — pas juste une ligne.
    from testpilot.api.services import attachment_service
    for p in pieces:
        assert (attachment_service.dossier(resultat["id"]) / p["stored_name"]).exists()


def test_sans_dossier_de_captures_aucune_piece_jointe_et_aucune_erreur(conn, campagne,
                                                                        monkeypatch):
    """Le cas normal aujourd'hui (aucune capture archivée) ne doit rien casser."""
    monkeypatch.setattr(run_service.explication, "propose_explication",
                        lambda verdict, **k: ("", 0.0))

    run_service._persist(conn, campagne["execution"], campagne["cas"], _verdict_passed(),
                         _OutcomeVide(), 1.2, "nominal")

    resultat = ResultRepo(conn).dernier(campagne["run"], campagne["cas"])
    assert ResultRepo(conn).pieces_jointes(resultat["id"]) == []
