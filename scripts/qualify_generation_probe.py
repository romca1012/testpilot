"""Génération réelle diagnostique sur un cas existant, sans exécution métier.

La base source est ouverte en lecture seule. Les sorties sont isolées ; elles ne remplacent
jamais une version utilisateur. Ce probe n'est pas la campagne statistique de qualification.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from testpilot import config
from testpilot.analysis.plan import TestPlan, ScenarioIntent
from testpilot.connectors.factory import build_connector
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation.agent import GenerationAgent
from testpilot.generation.qualification_budget import QualificationBudget, QualificationLLM
from testpilot.store.repositories import ProjectRepo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=int, required=True)
    parser.add_argument('--trial', required=True)
    args = parser.parse_args()
    if not args.trial.replace('-', '').replace('_', '').isalnum():
        parser.error('trial doit être un identifiant simple')
    out = ROOT / '.local-preview' / 'qualification' / args.trial
    out.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect((ROOT / 'data/testpilot.db').as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        project = ProjectRepo(conn).get(12)
        row = conn.execute('SELECT v.* FROM test_case c JOIN module m ON m.id=c.module_id '
                           'JOIN test_case_version v ON v.id=c.current_version_id '
                           'WHERE c.id=? AND m.project_id=12 AND c.deleted_at=\'\'', (args.case,)).fetchone()
    if not row or not project or project['base_url'] != 'https://sapian-portail-integration-38039788.dev.odoo.com':
        raise ValueError('Cas ou staging différent du périmètre approuvé')
    source = dict(row)
    metier = {'title': source['title'], 'preconditions': source['preconditions'],
              'steps': json.loads(source['test_steps']), 'expected_result': source['expected_result']}
    config.GENERATED_DIR = out / 'generated'
    config.GENERATED_DIR.mkdir()
    # Les notes et la mémoire sources restent en lecture seule : aucun runner réel ici.
    plan = TestPlan(module_name=args.trial, models=[], scenarios=[ScenarioIntent(
        name=metier['title'], type='nominal', action=' ; '.join(metier['steps']),
        persona='utilisateur de recette', expected_outcome=metier['expected_result'])],
        personas=['utilisateur de recette'], portal_routes=[], risks=[],
        raw_spec=json.dumps(metier, ensure_ascii=False))
    (out / 'input.json').write_text(json.dumps(metier, ensure_ascii=False, indent=2), encoding='utf-8')
    budget = QualificationBudget(out.parent / 'budget.db')
    connector = build_connector(project)
    runner = BehaveRunner(generated_dir=config.GENERATED_DIR, connector_type='odoo', project_id=12)
    runner.cibler_artefacts(out / 'dry-run')
    report = {'case_id': args.case, 'trial': args.trial, 'scope': 'diagnostic_generation_only'}
    try:
        connector.connect()
        result = GenerationAgent(llm=QualificationLLM(budget, args.trial,
                                 secrets=(project['password'], config.ANTHROPIC_API_KEY)), connector=connector,
                                 dry_runner=runner).generate(plan, metier=metier,
                                                            projet=project, qualification=True)
        report['generation'] = asdict(result)
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        report['error'] = str(exc).replace(project['password'], '[secret]')[:1500]
    finally:
        connector.disconnect()
        report['budget'] = budget.summary()
        budget.conn.close()
        (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'trial': args.trial, 'success': report.get('generation', {}).get('success'),
                      'error_type': report.get('error_type'), 'budget': report['budget']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
