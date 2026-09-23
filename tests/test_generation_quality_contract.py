"""Régressions qualité : artefacts exécutables et diagnostics exploitables."""
import pytest

from testpilot.execution.behave_result import BehaveResult
from testpilot.generation.react_loop import _maybe_dry_run
from testpilot.generation.smoke_check import smoke_check
from testpilot.generation.state import AgentState
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import write_feature_file


@pytest.mark.parametrize('body', [
    'Fonctionnalité: vide\n',
    'Fonctionnalité: vide\n  Scénario: sans étapes\n',
    'Fonctionnalité: vide\n  Plan du scénario: sans exemples\n    Quand action <x>\n',
    'ceci ne constitue pas du Gherkin',
])
def test_feature_inexecutable_ne_remplace_pas_le_fichier(tmp_path, body):
    path = tmp_path / 'demo.feature'
    path.write_text('ancien contenu', encoding='utf-8')
    result = write_feature_file(ToolContext('demo', tmp_path), body)
    assert not result.ok
    assert path.read_text(encoding='utf-8') == 'ancien contenu'


def test_outline_avec_exemples_est_executable(tmp_path):
    body = ('Fonctionnalité: F\n  Plan du scénario: exemple\n'
            '    Quand action <x>\n    Exemples:\n      | x |\n      | a |\n      | b |\n')
    result = write_feature_file(ToolContext('demo', tmp_path), body)
    assert result.ok
    assert '2 scénario(s)' in result.observation


def test_diagnostics_distincts_ne_declenchent_pas_un_faux_stall():
    from types import SimpleNamespace
    state = AgentState(module_name='demo', feature_written=True, steps_written=True)
    def run(message):
        runner = SimpleNamespace(dry_run=lambda _: BehaveResult(
            success=False, returncode=1, raw_stdout=message))
        return _maybe_dry_run(state, runner, stall_limit=1)
    assert run('ModuleNotFoundError: missing_one') == 'failed'
    assert 'missing_one' in state.messages[-1]['content'][0]['text']
    assert run('SyntaxError: missing colon') == 'failed'
    assert 'missing colon' in state.messages[-1]['content'][0]['text']
    assert run('SyntaxError: missing colon') == 'stalled'


@pytest.mark.parametrize('pages', [{}, {'/home': {'champs': []}}])
def test_menu_invente_signale_meme_sans_crawl_portail(pages):
    model = {'pages': pages, 'mesure_le': '2026-09-22',
             'modeles_backoffice': [{'menu': 'Assistance / Tickets', 'model': 'helpdesk.ticket'}]}
    warnings = smoke_check('Quand je navigue vers le menu Odoo "Helpdesk / All Tickets"', modele=model)
    assert len(warnings) == 1
    assert warnings[0]['kind'] == 'menu_non_observe'
    assert warnings[0]['line'] == 1
    assert '2026-09-22' in warnings[0]['message']
    assert smoke_check('Quand je navigue vers le menu Odoo "Assistance"', modele=model) == []
    assert smoke_check('Quand je navigue vers le menu Odoo "Assistance / Tickets"', modele=model) == []


def test_pas_de_preuve_menu_ne_fabrique_pas_un_avis():
    assert smoke_check('Quand je navigue vers le menu Odoo "Helpdesk"', modele={}) == []


def test_outline_vide_ne_se_cache_pas_derriere_un_scenario_valide(tmp_path):
    body = ('Fonctionnalité: F\n  Scénario: valide\n    Quand action\n'
            '  Plan du scénario: vide\n    Quand action <x>\n')
    assert not write_feature_file(ToolContext('demo', tmp_path), body).ok


def test_chemin_mesure_prioritaire_sur_le_libelle_feuille():
    model = {'modeles_backoffice': [{'menu': 'Tickets',
             'menu_path': 'Assistance / Tickets', 'model': 'helpdesk.ticket'}]}
    assert smoke_check('Quand je navigue vers le menu Odoo "Assistance / Tickets"', modele=model) == []
    assert smoke_check('Quand je navigue vers le menu Odoo "Ventes / Tickets"', modele=model)


def test_audit_distingue_donnees_invalides_et_exclut_rejeux_et_en_cours(tmp_path):
    import sqlite3

    from scripts.audit_generation_quality import audit
    path = tmp_path / 'audit.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE execution (execution_status, functional_status, started_at, '
                     'trigger, duration_seconds, scenarios_total, error_message)')
        conn.executemany('INSERT INTO execution VALUES (?, ?, ?, ?, ?, ?, ?)', [
            ('success', 'conforme', '2026-09-22', 'first_run', 1, 1, ''),
            ('success', 'non_conforme', '2026-09-22', 'first_run', 1, 1, ''),
            ('success', 'donnee_invalide', '2026-09-22', 'first_run', 1, 1, ''),
            ('technical_error', 'indetermine', '2026-09-22', 'first_run', 1, 1, ''),
            ('success', 'conforme', '2026-09-22', 'rerun', 1, 1, ''),
            ('not_executed', 'indetermine', '2026-09-22', 'first_run', 0, 0, ''),
        ])
    before = path.read_bytes()
    result = audit(path)
    assert result['total'] == 4
    assert result['technical_success_rate'] == .75
    assert result['usable_functional_verdict_rate'] == .5
    assert path.read_bytes() == before


def test_audit_base_absente_ne_cree_pas_de_fichier(tmp_path):
    import sqlite3

    from scripts.audit_generation_quality import audit
    path = tmp_path / 'absent.db'
    with pytest.raises(sqlite3.OperationalError):
        audit(path)
    assert not path.exists()
