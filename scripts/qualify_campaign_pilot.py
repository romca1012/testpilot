"""Campagne pilote (REDUITE) du Lot 5 -- generalise le 23/09/2026 pour accepter n'importe quel
projet/cas Odoo (--project-id/--cases/--iterations), plutot que les 2 cas (127, 128) du projet 12
codes en dur a l'origine. Par defaut (aucun argument), le comportement reste celui du pilote
d'origine : 2 cas du projet 12, 3 generations independantes chacun, une seule execution physique
par generation.

Perimetre reduit, approuve explicitement le 23/09/2026 : le corpus complet du plan (30 cas,
20 Odoo + 10 web) n'existe pas encore -- 0 cas web-generique defini. Ce script ne pretend PAS
qualifier le Lot 5 au sens du plan approuve (seuils 86/90, 27/30, etc, non applicables a un
petit echantillon) -- il mesure un signal reel sur les cas explicitement demandes, avec la meme
rigueur de protocole que possible a cette echelle : generation independante, execution physique
unique (aucun rejeu, aucune reparation, aucune resolution adaptative -- TESTPILOT_QUALIFICATION=1),
isolation des memoires apprises entre les essais d'un meme cas, verification independante
(requete RPC fraiche, hors des assertions du Gherkin genere).

Sans --expected-base-url explicite, un projet different du projet 12 par defaut ne verifie AUCUNE
URL attendue avant de lancer -- l'appelant est responsable d'avoir confirme que la cible (base_url
du projet en base) est la bonne avant de lancer une campagne qui va reellement creer des
enregistrements dessus.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

# ⚠️ ISOLATION DES DONNEES (2026-09-24) : une mesure ne modifie JAMAIS les memoires apprises de
# production (`data/`). La campagne tourne sur une COPIE horodatee (`TESTPILOT_DATA_DIR`), posee
# AVANT tout import de `testpilot` (config.DATA_DIR et les dossiers de memoire en derivent a
# l'import) et heritee par les sous-processus Behave. Ce qu'une campagne apprend est examine
# puis importe EXPLICITEMENT, jamais ecrit en production par effet de bord. Cause : le
# 2026-09-24, `_restaurer_memoires` a supprime `data/selecteurs/projet-1.jsonl` pendant qu'une
# suite pytest tournait, et la garde « donnees reelles » a fait echouer un test sans rapport.
# Regle operationnelle : ne jamais lancer la suite pytest et une campagne en meme temps.
#
# ⚠️ **La cle de chiffrement n'est JAMAIS copiee sur disque** : `secrets.py` lit
# `TESTPILOT_SECRET_KEY` en priorite — on la lit a sa SOURCE et on la transmet par l'environnement
# du processus (herite par Behave). La copie de la base ne contient que des mots de passe chiffres,
# inutilisables sans elle. Les copies au-dela des `_COPIES_A_GARDER` plus recentes sont purgees.
# ⚠️ Non isole : `config.GENERATED_DIR` (sous `behave_runtime/`, pas sous `DATA_DIR`) — le script
# le redirige lui-meme vers le dossier de chaque essai (`config.GENERATED_DIR = trial_dir / …`).
_A_COPIER = ('testpilot.db', 'domain', 'menus-appris', 'selecteurs', 'regles-apprises',
             'specifications')
_COPIES_A_GARDER = 3


def _poser_cle_depuis_source(source: Path) -> bool:
    """Lit `<source>/.secret_key` et la pose dans `TESTPILOT_SECRET_KEY` (sans ecraser une valeur
    deja fournie par l'environnement). Rend vrai si une cle est disponible pour le processus."""
    if os.environ.get('TESTPILOT_SECRET_KEY', '').strip():
        return True
    fichier = source / '.secret_key'
    if fichier.is_file():
        os.environ['TESTPILOT_SECRET_KEY'] = fichier.read_text(encoding='utf-8').strip()
        return True
    return False


def _purger_anciennes_copies(qualif: Path, garder: int = _COPIES_A_GARDER) -> list:
    copies = sorted(qualif.glob('*/data-*'), key=lambda d: d.name.rsplit('data-', 1)[-1],
                    reverse=True)
    purgees = []
    for ancienne in copies[garder:]:
        shutil.rmtree(ancienne, ignore_errors=True)
        purgees.append(str(ancienne))
    return purgees


def _isoler_donnees(out_name: str, source: Path | None = None, racine: Path = ROOT) -> Path:
    source = Path(source or os.environ.get('TESTPILOT_CAMPAIGN_SOURCE_DATA') or racine / 'data')
    horodatage = datetime.now().strftime('%Y%m%d-%H%M%S')
    qualif = racine / '.local-preview' / 'qualification'
    cible = qualif / out_name / f'data-{horodatage}'
    cible.mkdir(parents=True, exist_ok=False)
    try:
        cible.chmod(0o700)  # sans effet reel sous Windows (droits herites du profil utilisateur)
    except OSError:
        pass
    for nom in _A_COPIER:
        origine = source / nom
        if origine.is_dir():
            shutil.copytree(origine, cible / nom)
        elif origine.is_file():
            shutil.copy2(origine, cible / nom)
    _poser_cle_depuis_source(source)
    os.environ['TESTPILOT_DATA_DIR'] = str(cible)
    os.environ.pop('TESTPILOT_DB_PATH', None)
    for purgee in _purger_anciennes_copies(qualif):
        print(json.dumps({'copie_purgee': purgee}, ensure_ascii=True))
    return cible


def _masquer_secrets(texte: str, project: dict) -> str:
    """Retire d'un texte destine a un artefact TOUT secret connu : mot de passe du projet, cle API,
    cle de chiffrement (jamais ecrite dans un `result.json`, un rapport ou une trace)."""
    for secret in (project.get('password'), os.environ.get('TESTPILOT_SECRET_KEY'),
                   os.environ.get('ANTHROPIC_API_KEY')):
        if secret and len(str(secret)) >= 6:
            texte = texte.replace(str(secret), '[secret]')
    return texte


def _nom_de_sortie_demande() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == '--out' and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith('--out='):
            return arg.split('=', 1)[1]
    return ''


DATA_DIR_ISOLE = _isoler_donnees(_nom_de_sortie_demande()) if _nom_de_sortie_demande() else None

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

DEFAULT_PROJECT_ID = 12
DEFAULT_CASE_IDS = (127, 128)
DEFAULT_ITERATIONS = (1, 2, 3)
DEFAULT_EXPECTED_BASE_URL = 'https://sapian-portail-integration-38039788.dev.odoo.com'

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


def _charger_metier(conn, case_id: int, project_id: int) -> dict:
    row = conn.execute(
        'SELECT v.* FROM test_case c JOIN module m ON m.id=c.module_id '
        'JOIN test_case_version v ON v.id=c.current_version_id '
        'WHERE c.id=? AND m.project_id=? AND c.deleted_at=\'\'', (case_id, project_id)).fetchone()
    if not row:
        raise ValueError(f'cas {case_id} introuvable pour le projet {project_id}')
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
             budget: QualificationBudget, project_id: int) -> dict:
    trial = f'pilote-p{project_id}-c{case_id}-i{iteration}-20260923'
    trial_dir = out_dir / trial
    trial_dir.mkdir(parents=True)

    with sqlite3.connect(config.DB_PATH.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        metier = _charger_metier(conn, case_id, project_id)

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

    rapport = {'case_id': case_id, 'iteration': iteration, 'trial': trial,
              'data_dir': str(config.DATA_DIR)}
    os.environ['TESTPILOT_QUALIFICATION'] = '1'
    connector = build_connector(project)
    dry_runner = BehaveRunner(generated_dir=config.GENERATED_DIR, connector_type='odoo',
                              project_id=project_id, connection=connexion)
    dry_runner.cibler_artefacts(trial_dir / 'generation')
    debut = time.time()
    try:
        connector.connect()
        result = GenerationAgent(
            llm=QualificationLLM(budget, trial, secrets=(project['password'], config.ANTHROPIC_API_KEY,
                                                          os.environ.get('TESTPILOT_SECRET_KEY'))),
            connector=connector, dry_runner=dry_runner,
        ).generate(plan, metier=metier, projet=project, qualification=True)
        rapport['generation'] = asdict(result)
    except Exception as exc:
        rapport['generation_error_type'] = type(exc).__name__
        rapport['generation_error'] = _masquer_secrets(str(exc), project)[:1500]
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
                              project_id=project_id, connection=connexion)
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
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--out', required=True)
    parser.add_argument('--project-id', type=int, default=DEFAULT_PROJECT_ID)
    parser.add_argument('--cases', type=str, default=None,
                        help='ids de cas separes par des virgules (defaut : pilote 127,128)')
    parser.add_argument('--iterations', type=str, default=None,
                        help='numeros d\'iteration separes par des virgules (defaut : 1,2,3)')
    parser.add_argument('--expected-base-url', type=str, default=None,
                        help='garde-fou : refuse de lancer si le project.base_url differe')
    args = parser.parse_args()
    # ⚠️ Echec BRUYANT si l'isolation n'est pas active (revue verdict-reviewer, 2026-09-24) : un
    # `--out` mal reconnu par l'analyse precoce de `sys.argv`, ou un `TESTPILOT_DB_PATH` reinjecte
    # par `.env`, ferait sinon tourner la campagne sur le `data/` REEL sans aucune erreur.
    if DATA_DIR_ISOLE is None:
        raise SystemExit("isolation des donnees inactive (--out non reconnu) : campagne refusee")
    if Path(config.DATA_DIR).resolve() != DATA_DIR_ISOLE.resolve():
        raise SystemExit(f"config.DATA_DIR ({config.DATA_DIR}) n'est pas la copie isolee")
    if DATA_DIR_ISOLE.resolve() not in Path(config.DB_PATH).resolve().parents:
        raise SystemExit(f"config.DB_PATH ({config.DB_PATH}) est hors de la copie isolee : "
                         "campagne refusee (TESTPILOT_DB_PATH reinjecte par .env ?)")
    project_id = args.project_id
    case_ids = tuple(int(c) for c in args.cases.split(',')) if args.cases else DEFAULT_CASE_IDS
    iterations = (tuple(int(i) for i in args.iterations.split(','))
                 if args.iterations else DEFAULT_ITERATIONS)
    expected_base_url = (args.expected_base_url if args.expected_base_url is not None
                        else (DEFAULT_EXPECTED_BASE_URL if project_id == DEFAULT_PROJECT_ID else None))
    out_dir = ROOT / '.local-preview' / 'qualification' / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({'data_dir_isole': str(config.DATA_DIR)}, ensure_ascii=True))

    with sqlite3.connect(config.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        project = ProjectRepo(conn).get(project_id)
    if project is None:
        raise ValueError(f'projet {project_id} introuvable')
    if expected_base_url is not None and project['base_url'] != expected_base_url:
        raise ValueError(
            f'projet {project_id} : base_url {project["base_url"]!r} differe du perimetre '
            f'approuve {expected_base_url!r} -- passe --expected-base-url pour confirmer '
            f'explicitement un changement de cible.')
    connexion = verifier_connexion(project)

    budget = QualificationBudget(out_dir / 'budget.db')
    resultats = []
    for case_id in case_ids:
        for iteration in iterations:
            snapshot = _snapshot_memoires(project_id)
            try:
                rapport = _un_essai(case_id, iteration, out_dir, project, connexion, budget,
                                    project_id)
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
