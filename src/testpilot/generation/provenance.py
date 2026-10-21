"""Empreintes du contexte, sans recopier les secrets de connexion."""
from __future__ import annotations

import hashlib
import json


def fingerprint(value) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def target_fingerprint(project: dict | None, *, compte: str | None = None) -> str:
    """`compte` (étape 4, morceau 7) : l'empreinte du compte dont les écrans ont été observés — une preuve prise avec le
    principal ne vaut pas pour un test écrit pour Lecteur (A64 : « même cible »). Sans lui : l'empreinte d'avant, inchangée."""
    p = project or {}
    cible = {key: p.get(key) for key in ('id', 'base_url', 'database', 'username', 'connector_type', 'connector_version')}
    if compte:
        cible['compte'] = compte
    return fingerprint(cible)


def revision_metadata(version: dict | None) -> dict:
    """Conserve les observations, sans certifier le plan d'un script modifié.

    Étape 2 (A61, 2026-10-20) : une version jamais instrumentée (`''` : saisie à la main, antérieure aux preuves) le reste
    — elle devenait `'[]'` (« instrumentée, rien vu ») à sa première copie, et tous ses champs sortaient « sans preuve ».
    Même distinction que `verified_fields` (None ≠ {}). Une génération écrit toujours une liste, même vide."""
    version = version or {}
    origin = json.loads(version.get('generation_provenance') or '{}')
    return {
        'observation_evidence': version.get('observation_evidence') or '',
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
