"""Campagne pilote (REDUITE) du Lot 5 -- 2 cas Odoo reels (127, 128), 3 generations
independantes chacun, une seule execution physique par generation.

Perimetre reduit, approuve explicitement le 23/09/2026 : le corpus complet du plan (30 cas,
20 Odoo + 10 web) n'existe pas encore -- 0 cas web-generique defini, et le projet 1 (22 cas
Odoo) pointe vers un Odoo local injoignable au moment de ce pilote. Ce script ne pretend PAS
qualifier le Lot 5 au sens du plan approuve (seuils 86/90, 27/30, etc, non applicables a un
echantillon de 6 essais) -- il mesure un signal reel sur les 2 seuls cas actuellement joignables
(projet 12, staging Sapian), avec la meme rigueur de protocole que possible a cette echelle :
generation independante, execution physique unique (aucun rejeu, aucune reparation, aucune
resolution adaptative -- TESTPILOT_QUALIFICATION=1), isolation des memoires apprises entre les
3 essais d'un meme cas, verification independante (requete RPC fraiche, hors des assertions du
Gherkin genere).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from testpilot import config
from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.connectors.factory import build_connector
from testpilot.connectors.runtime_env import verifier_connexion
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.generation import menu_appris
from testpilot.generation import regles_apprises
from testpilot.generation.agent import GenerationAgent
from testpilot.generation.qualification_budget import QualificationBudget, QualificationLLM
from testpilot.execution import selector_memory
from testpilot.store.repositories import CaseRepo, ProjectRepo
from testpilot.verdict.status import derive_verdict

PROJECT_ID = 12
CASE_IDS = (127, 128)
ITERATIONS = (1, 2, 3)
EXPECTED_BASE_URL = 'https://sapian-portail-integration-38039788.dev.odoo.com'

MEMOIRES = (menu_appris, selector_memory, regles_apprises)


def _snapshot_memoires(project_id: int) -> dict:
    """Contenu BRUT (ou absence) de chaque fichier de memoire, pour restauration exacte."""
    snap = {}
    for module in MEMOIRES:
        chemin = module.chemin(project_id)
        snap[chemin] = chemin.read_bytes() if chemin.exists() else None
    return snap


def _restaurer_memoires(snapshot: dict) -> None:
    for chemin, contenu in snapshot.items():
        if contenu is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(contenu)
    for module in MEMOIRES:
        module._lire.cache_clear()


def _charger_metier(conn, case_id: int) -> dict:
    row = conn.execute(
        'SELECT v.* FROM test_case c JOIN module m ON m.id=c.module_id '
        'JOIN test_case_version v ON v.id=c.current_version_id '
        'WHERE c.id=? AND m.project_id=? AND c.deleted_at=\'\'', (case_id, PROJECT_ID)).fetchone()
    if not row:
        raise ValueError(f'cas {case_id} introuvable pour le projet {PROJECT_ID}')
    source = dict(row)
    return {'title': source['title'], 'preconditions': source['preconditions'],
           'steps': json.loads(source['test_steps']), 'expected_result': source['expected_result']}


def _verification_independante(connector, model: str, since_epoch: float) -> dict:
    """Requete RPC FRAICHE, jamais celle du Gherkin genere : combien d'enregistrements du
    modele ont ete crees depuis le debut de CET essai ? Independant du mecanisme de comptage
    interne au scenario (memorize_record_count / check_count_increased_by_one).

    Corrige apres le pilote du 23/09/2026 -- deux bugs dans la version precedente :
    1. `time.mktime` interprete le `write_date` (deja en UTC cote Odoo) comme une heure LOCALE --
       decalage silencieux qui faisait echouer la comparaison, jamais un `nouveaux > 0` meme sur
       un essai reellement reussi. `datetime.fromtimestamp(..., tz=timezone.utc)` construit le
       seuil explicitement en UTC, comparable tel quel a `write_date`.
    2. `search(model, [], limit=0)` ramenait TOUS les ids du modele (37 955 tickets mesures) puis
       les lisait un par un cote client -- source du `TimeoutError` systematique sur
       `helpdesk.ticket`. Le filtre `write_date >= seuil` est desormais applique COTE SERVEUR
       (domaine de recherche), avec une limite de securite : la requete ne ramene plus jamais
       qu'une poignee d'ids, jamais le modele entier.
    """
    try:
        seuil_iso = datetime.fromtimestamp(since_epoch - 5, tz=timezone.utc).strftime(
            '%Y-%m-%d %H:%M:%S')
        ids = connector.search(model, [('write_date', '>=', seuil_iso)], limit=50)
        return {'ok': True, 'nouveaux': len(ids), 'erreur': ''}
    except Exception as exc:
        return {'ok': False, 'nouveaux': 0, 'erreur': f'{type(exc).__name__}: {exc}'}


def _un_essai(case_id: int, iteration: int, out_dir: Path, project: dict, connexion: dict,
             budget: QualificationBudget) -> dict:
    trial = f'pilote-c{case_id}-i{iteration}-20260923'
    trial_dir = out_dir / trial
    trial_dir.mkdir(parents=True)

    with sqlite3.connect((ROOT / 'data/testpilot.db').as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        metier = _charger_metier(conn, case_id)

    config.GENERATED_DIR = trial_dir / 'generated'
    config.GENERATED_DIR.mkdir()
    module_name = trial.replace('-', '_')
    plan = TestPlan(module_name=module_name, models=[], scenarios=[ScenarioIntent(
        name=metier['title'], type='nominal', action=' ; '.join(metier['steps']),
        persona='utilisateur de recette', expected_outcome=metier['expected_result'])],
        personas=['utilisateur de recette'], portal_routes=[], risks=[],
        raw_spec=json.dumps(metier, ensure_ascii=False))
    (trial_dir / 'input.json').write_text(json.dumps(metier, ensure_ascii=False, indent=2),
                                          encoding='utf-8')

    rapport = {'case_id': case_id, 'iteration': iteration, 'trial': trial}
    os.environ['TESTPILOT_QUALIFICATION'] = '1'
    connector = build_connector(project)
    dry_runner = BehaveRunner(generated_dir=config.GENERATED_DIR, connector_type='odoo',
                              project_id=PROJECT_ID, connection=connexion)
    dry_runner.cibler_artefacts(trial_dir / 'generation')
    debut = time.time()
    try:
        connector.connect()
        result = GenerationAgent(
            llm=QualificationLLM(budget, trial, secrets=(project['password'], config.ANTHROPIC_API_KEY)),
            connector=connector, dry_runner=dry_runner,
        ).generate(plan, metier=metier, projet=project, qualification=True)
        rapport['generation'] = asdict(result)
    except Exception as exc:
        rapport['generation_error_type'] = type(exc).__name__
        rapport['generation_error'] = str(exc).replace(project['password'], '[secret]')[:1500]
        connector.disconnect()
        rapport['budget'] = budget.summary()
        (trial_dir / 'result.json').write_text(json.dumps(rapport, ensure_ascii=False, indent=2,
                                                          default=str), encoding='utf-8')
        return rapport

    gen = rapport['generation']
    if not gen.get('success') or not gen.get('dry_run_passed'):
        rapport['execution'] = None
        connector.disconnect()
        rapport['budget'] = budget.summary()
        (trial_dir / 'result.json').write_text(json.dumps(rapport, ensure_ascii=False, indent=2,
                                                          default=str), encoding='utf-8')
        return rapport

    # Execution physique UNIQUE : max_retries=0, meme sous TESTPILOT_QUALIFICATION=1 (deja
    # sans resolution adaptative -- verifie plus haut dans le module _base_helpers).
    run_runner = BehaveRunner(generated_dir=config.GENERATED_DIR, connector_type='odoo',
                              project_id=PROJECT_ID, connection=connexion)
    run_runner.cibler_artefacts(trial_dir / 'execution')
    outcome = Executor(run_runner, max_retries=0).execute(module_name)
    verdict = derive_verdict(outcome, connector_type='odoo')
    rapport['execution'] = {
        'execution_status': verdict.execution_status, 'functional_status': verdict.functional_status,
        'dry_run_passed': outcome.dry_run_passed, 'retried': outcome.retried,
        'physical_attempts': len(outcome.attempts), 'error': outcome.error,
    }

    modele_teste = (metier.get('title') or '').lower()
    modele_rpc = 'survey.survey' if 'sondage' in modele_teste else 'helpdesk.ticket'
    rapport['verification_independante'] = _verification_independante(connector, modele_rpc, debut)

    connector.disconnect()
    rapport['budget'] = budget.summary()
    (trial_dir / 'result.json').write_text(json.dumps(rapport, ensure_ascii=False, indent=2,
                                                      default=str), encoding='utf-8')
    return rapport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out_dir = ROOT / '.local-preview' / 'qualification' / args.out
    out_dir.mkdir(parents=True, exist_ok=False)

    with sqlite3.connect(ROOT / 'data' / 'testpilot.db') as conn:
        conn.row_factory = sqlite3.Row
        project = ProjectRepo(conn).get(PROJECT_ID)
    if project is None or project['base_url'] != EXPECTED_BASE_URL:
        raise ValueError('projet 12 introuvable ou staging different du perimetre approuve')
    connexion = verifier_connexion(project)

    budget = QualificationBudget(out_dir / 'budget.db')
    resultats = []
    for case_id in CASE_IDS:
        for iteration in ITERATIONS:
            snapshot = _snapshot_memoires(PROJECT_ID)
            try:
                rapport = _un_essai(case_id, iteration, out_dir, project, connexion, budget)
            finally:
                _restaurer_memoires(snapshot)
            resultats.append(rapport)
            gen = rapport.get('generation') or {}
            exe = rapport.get('execution') or {}
            verif = rapport.get('verification_independante') or {}
            print(json.dumps({
                'case_id': case_id, 'iteration': iteration,
                'generation_success': gen.get('success'), 'dry_run_passed': gen.get('dry_run_passed'),
                'execution_status': exe.get('execution_status'),
                'functional_status': exe.get('functional_status'),
                'verif_independante_nouveaux': verif.get('nouveaux'),
                'cost_usd': gen.get('cost_usd'),
                'budget_total_usd': rapport.get('budget', {}).get('charged_or_reserved_usd'),
            }, ensure_ascii=True))

    (out_dir / 'campagne.json').write_text(json.dumps(resultats, ensure_ascii=False, indent=2,
                                                       default=str), encoding='utf-8')
    budget.conn.close()


if __name__ == '__main__':
    main()
