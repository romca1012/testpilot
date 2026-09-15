"""Étape 2.2 du plan de consolidation (audit « Le pari Mabl/Testim », 2026-09-15) : le verdict
d'un cas générique (`GenericWebConnector`, aucune méthode RPC) ne peut constater que ce que l'UI
affiche, jamais une vérité côté base de données comme un cas Odoo. `CaseVerdict.ground_truth`
étiquette cette différence — vérifié en isolation dans `test_status_two_axes.py` ; ce fichier
vérifie que `run_service._execute_and_persist` transmet réellement le CONNECTEUR DU PROJET à
`derive_verdict`, pas seulement en théorie.
"""

from __future__ import annotations

from testpilot.api.services import run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
)


class _RunnerFactice:
    """Même patron que `test_reexecution_script_disparu.py::_RunnerFactice` — aucun Behave ni
    Playwright réel, juste de quoi prouver le BRANCHEMENT."""

    def cibler_artefacts(self, _chemin):
        pass

    def cibler_execution(self, _execution_id):
        pass

    def dry_run(self, _module_name):
        return BehaveResult(success=True, returncode=0, dry_run=True)

    def real_run(self, _module_name):
        return BehaveResult(success=True, returncode=0,
                            scenarios=[BehaveScenario(name="rien à vérifier", status="passed")])


def _projet_avec_cas(conn, *, connector_type: str):
    pid = ProjectRepo(conn).create(name=f"Démo {connector_type}", connector_type=connector_type,
                                   base_url="https://example.invalid", database="",
                                   username="", password="")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="demo")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="", steps_content="")
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


def test_execute_and_persist_transmet_le_connector_type_du_projet(tmp_path, monkeypatch):
    """LE branchement : sans lui, `derive_verdict` retomberait toujours sur son défaut
    `backend_verified`, quel que soit le connecteur réel du projet."""
    monkeypatch.setattr("testpilot.config.DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(tmp_path / "d.db")
    recus = []
    vrai_derive_verdict = run_service.derive_verdict

    def _espion(outcome, **kw):
        recus.append(kw.get("connector_type"))
        return vrai_derive_verdict(outcome, **kw)

    monkeypatch.setattr(run_service, "derive_verdict", _espion)
    try:
        cid, _vid, eid = _projet_avec_cas(conn, connector_type="web")

        run_service._execute_and_persist(conn, eid, cid, "demo", _RunnerFactice())

        execution = ExecutionRepo(conn).get(eid)
    finally:
        conn.close()

    assert recus == ["web"]
    assert execution["execution_status"] == "success"
    assert execution["functional_status"] == "conforme"


def test_un_projet_odoo_transmet_bien_odoo(tmp_path, monkeypatch):
    monkeypatch.setattr("testpilot.config.DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(tmp_path / "d.db")
    recus = []
    vrai_derive_verdict = run_service.derive_verdict

    def _espion(outcome, **kw):
        recus.append(kw.get("connector_type"))
        return vrai_derive_verdict(outcome, **kw)

    monkeypatch.setattr(run_service, "derive_verdict", _espion)
    try:
        cid, _vid, eid = _projet_avec_cas(conn, connector_type="odoo")
        run_service._execute_and_persist(conn, eid, cid, "demo", _RunnerFactice())
    finally:
        conn.close()

    assert recus == ["odoo"]
