"""Qualification : première tentative, intégrité des traces et frontières des preuves."""
import json
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.execution.behave_result import BehaveFailure, BehaveResult, BehaveScenario
from testpilot.execution.executor import Executor
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo, ExecutionRepo, ensure_default_module
from testpilot.store.execution_attempts import ExecutionAttemptRepo, summarize_first_attempts


def passed():
    return BehaveResult(True, 0, scenarios=[BehaveScenario('cas', 'passed')])


def timeout():
    return BehaveResult(False, 1, scenarios=[BehaveScenario('cas', 'failed')],
                        failures=[BehaveFailure('cas', 'click', 'ui_timeout', 'TimeoutError')])


@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    c = get_initialized_db(tmp_path / 'attempts.db')
    mid = ensure_default_module(c, 'm')
    cid = CaseRepo(c).create(title='cas', module_id=mid, feature_slug='cas')
    vid = VersionRepo(c).create(test_case_id=cid, spec_content='spec', spec_hash='h',
                                feature_content='feature', steps_content='steps')
    eid = ExecutionRepo(c).create(test_case_id=cid, version_id=vid)
    yield c, eid, cid
    c.close()


def test_rejeu_ne_remplace_ni_premier_resultat_ni_artefacts(execution, tmp_path):
    from testpilot.api.services.run_service import _execute_and_persist
    c, eid, cid = execution
    class Runner:
        number = 0
        def cibler_artefacts(self, path): self.path = path
        def dry_run(self, _): return BehaveResult(True, 0)
        def real_run(self, _):
            self.number += 1
            self.path.mkdir(parents=True, exist_ok=True)
            (self.path / 'execution.log').write_text(str(self.number))
            return timeout() if self.number == 1 else passed()
    result = _execute_and_persist(c, eid, cid, 'cas', Runner())
    assert result.retried and len(result.attempts) == 2
    rows = ExecutionAttemptRepo(c).list_for_execution(eid)
    assert [r['execution_status'] for r in rows] == ['technical_error', 'success']
    from pathlib import Path
    assert [Path(r['artifacts_path'], 'execution.log').read_text() for r in rows] == ['1', '2']
    summary = summarize_first_attempts(c)
    assert summary['ran_rate'] == 0 and summary['retried'] == 1
    assert ExecutionRepo(c).get(eid)['execution_status'] == 'success'


def test_qualification_interdit_le_rejeu(execution):
    from testpilot.api.services.run_service import _execute_and_persist
    c, eid, cid = execution
    runner = SimpleNamespace(dry_run=lambda _: BehaveResult(True, 0), real_run=lambda _: timeout())
    result = _execute_and_persist(c, eid, cid, 'cas', runner, qualification=True)
    assert not result.retried and len(result.attempts) == 1
    row = ExecutionAttemptRepo(c).list_for_execution(eid)[0]
    assert json.loads(row['provenance'])['qualification'] is True


def test_exception_physique_conserve_le_diagnostic(execution):
    from testpilot.api.services.run_service import _execute_and_persist
    c, eid, cid = execution
    def crash(_): raise RuntimeError('runner interrompu')
    runner = SimpleNamespace(dry_run=lambda _: BehaveResult(True, 0), real_run=crash)
    with pytest.raises(RuntimeError, match='runner interrompu'):
        _execute_and_persist(c, eid, cid, 'cas', runner)
    row = ExecutionAttemptRepo(c).list_for_execution(eid)[0]
    assert row['finished_at'] and row['execution_status'] == 'technical_error'
    assert 'runner interrompu' in row['result_json']


def test_historique_non_mesure_ne_devient_pas_zero(execution):
    c, _, _ = execution
    summary = summarize_first_attempts(c)
    assert summary['unmeasured'] == 1 and summary['ran_rate'] is None
    assert summarize_first_attempts(c, allowed_project_ids=[])['unmeasured'] == 0


def test_rpc_autre_page_et_autre_compte_ne_prouvent_pas_le_champ():
    from testpilot.generation.evidence import contextual_warnings
    feature = 'Quand je navigue vers "/form"\nEt je renseigne le champ "name" avec "test"'
    from datetime import datetime, timezone
    base = {'source': 'ui', 'resource': '/form', 'target_sha256': 'a',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'fields': [{'name': 'name', 'visible': True}]}
    assert contextual_warnings(feature, [base], target_sha256='a') == []
    for override in ({'source': 'rpc'}, {'resource': '/other'}, {'target_sha256': 'b'},
                     {'observed_at': '2020-01-01T00:00:00+00:00'},
                     {'fields': [{'name': 'name', 'visible': False}]}):
        assert contextual_warnings(feature, [{**base, **override}], target_sha256='a')
    assert contextual_warnings(feature, [{**base, 'resource': 'https://other.test/form'}],
                               target_sha256='a', base_url='https://target.test')


@pytest.mark.parametrize('payload', [{'content': []}, {}, 'bad'])
def test_arguments_invalides_n_ecrivent_rien(tmp_path, payload):
    from testpilot.generation.tools import dispatch, ToolContext
    result = dispatch('write_feature_file', payload, ToolContext('cas', tmp_path))
    assert not result.ok
    assert not list(tmp_path.iterdir())


def test_qualification_ne_soumet_pas_le_formulaire(tmp_path):
    from testpilot.generation.tools import dispatch, ToolContext
    def forbidden(*args): raise AssertionError('aucune soumission autorisée')
    ctx = ToolContext('cas', tmp_path, connector=SimpleNamespace(attempt_login=forbidden), qualification=True)
    result = dispatch('attempt_login', {'username': 'u', 'password': 'p'}, ctx)
    assert not result.ok and not ctx.calibration_attempts
    assert not dispatch('query_data', {'model': 'res.users', 'fields': ['password']}, ctx).ok


def test_revision_conserve_preuves_sans_certifier_le_nouveau_script(execution):
    c, eid, cid = execution
    vid = ExecutionRepo(c).get(eid)['version_id']
    proof = json.dumps([{'id': 'observation-1', 'source': 'ui', 'resource': '/form'}])
    c.execute('UPDATE test_case_version SET observation_evidence=?, generation_provenance=?, '
              'technical_plan=? WHERE id=?', (proof, '{"model":"original"}', '{"title":"ancien"}', vid))
    c.commit()
    CaseRepo(c).set_current_version(cid, vid)
    new_id = CaseRepo(c).update_script(cid, feature_content='changed', steps_content='new')
    revised = VersionRepo(c).get(new_id)
    assert revised['observation_evidence'] == proof
    assert revised['technical_plan'] == ''
    assert json.loads(revised['generation_provenance']) == {
        'derived_from_version': vid, 'origin': {'model': 'original'}}


def test_plan_compile_et_refuse_exigence_ou_preuve_inventee(tmp_path):
    from copy import deepcopy
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.technical_plan import write_test_plan
    ctx = ToolContext('cas', tmp_path)
    ctx.requirements = {'expected_result': 'Confirmation visible'}
    ctx.shared_steps = [SimpleNamespace(keyword='given', label='la page ouverte'),
                        SimpleNamespace(keyword='then', label='la confirmation visible')]
    plan = {'title': 'Confirmation', 'scenarios': [{'name': 'Succès',
        'requirement_ids': ['expected_result'], 'steps': [
            {'keyword': 'Soit', 'text': 'la page ouverte', 'evidence_ids': []},
            {'keyword': 'Alors', 'text': 'la confirmation visible', 'evidence_ids': []}]}]}
    assert write_test_plan(ctx, plan).ok
    original = (tmp_path / 'cas.feature').read_text(encoding='utf-8')
    assert 'Alors la confirmation visible' in original
    for mutate in ('proof', 'requirement', 'assertion', 'step', 'newline'):
        invalid = deepcopy(plan)
        scenario = invalid['scenarios'][0]
        if mutate == 'proof': scenario['steps'][0]['evidence_ids'] = ['inconnue']
        if mutate == 'requirement': scenario['requirement_ids'] = ['inventée']
        if mutate == 'assertion': scenario['steps'].pop()
        if mutate == 'step': scenario['steps'][0]['text'] = 'action inventée'
        if mutate == 'newline': invalid['title'] = 'Titre\nScénario: injecté'
        assert not write_test_plan(ctx, invalid).ok
        assert (tmp_path / 'cas.feature').read_text(encoding='utf-8') == original
