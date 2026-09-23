"""Empreintes du contexte, sans recopier les secrets de connexion."""
from __future__ import annotations

import hashlib
import json


def fingerprint(value) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def target_fingerprint(project: dict | None) -> str:
    p = project or {}
    return fingerprint({key: p.get(key) for key in (
        'id', 'base_url', 'database', 'username', 'connector_type', 'connector_version')})


def revision_metadata(version: dict | None) -> dict:
    """Conserve les observations, sans certifier le plan d'un script modifié."""
    version = version or {}
    origin = json.loads(version.get('generation_provenance') or '{}')
    return {
        'observation_evidence': version.get('observation_evidence') or '[]',
        'generation_provenance': json.dumps({
            'derived_from_version': version.get('id'), 'origin': origin,
        }, ensure_ascii=False),
        'technical_plan': '',
    }


def execution_provenance(conn, execution_id: int) -> dict:
    from testpilot.store.repositories import ExecutionRepo, VersionRepo, CaseRepo, ProjectRepo
    from testpilot.generation.domain_model import charger_modele
    execution = ExecutionRepo(conn).get(execution_id) or {}
    version = VersionRepo(conn).get(execution.get('version_id')) or {}
    case = CaseRepo(conn).get(execution.get('test_case_id')) or {}
    project = ProjectRepo(conn).get(case.get('project_id')) or {}
    return {'version_id': execution.get('version_id'),
            'artifact_sha256': fingerprint([version.get('feature_content'), version.get('steps_content')]),
            'target_sha256': target_fingerprint(project),
            'domain_sha256': fingerprint(charger_modele(project)),
            'generation': json.loads(version.get('generation_provenance') or '{}')}
