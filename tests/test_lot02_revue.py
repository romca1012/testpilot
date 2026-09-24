"""Lot 02 — points de la revue `verdict-reviewer` (2026-09-24).

1. Une cause n'est JAMAIS affichée brute (§4.7) : le libellé français du front reste le miroir exact
   de `defect_taxonomy.LABELS`.
2. Un constat écrit sous `@given`/`@step` serait classé `blocked` : le gate en avertit le relecteur.
3. La migration 48 ne saute plus une table en silence.
4. L'Alembic head accepte `blocked` (montée ET descente), sur SQLite au moins.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from testpilot.generation.assertion_lint import ASSERTION_DANS_CONTEXTE, lint_steps
from testpilot.store.db import _migrate_48_execution_blocked
from testpilot.verdict import defect_taxonomy as dt

RACINE = Path(__file__).resolve().parents[1]


# ── 1. Parité des libellés de cause : Python ↔ TypeScript ────────────────────────────────────

def _causes_du_front() -> dict:
    source = (RACINE / "frontend" / "src" / "lib" / "status.ts").read_text(encoding="utf-8")
    bloc = re.search(r"const CAUSE: Record<string, string> = \{(.*?)\n\}", source, re.S).group(1)
    return dict(re.findall(r"^\s*(\w+):\s*'([^']*)',?\s*$", bloc, re.M))


def test_le_front_libelle_exactement_les_memes_causes_que_le_serveur():
    front = _causes_du_front()

    assert front == dt.LABELS, "une cause ajoutée d'un seul côté s'afficherait brute ou fausse"


def test_toute_cause_de_la_taxonomie_a_un_libelle_francais():
    for cause in dt.CATEGORIES:
        assert dt.LABELS.get(cause), cause


def test_le_tableau_des_resultats_n_affiche_plus_la_cause_brute():
    source = (RACINE / "frontend" / "src" / "components" / "case" / "TestsResultsTab.vue").read_text(
        encoding="utf-8")

    assert "causeLabel(s.cause_category)" in source
    assert "{{ s.cause_category }}" not in source


# ── 2. Lint : un constat sous @given ─────────────────────────────────────────────────────────

_STEP_GIVEN_AVEC_ASSERT = '''
from behave import given

@given('le ticket est bien créé')
def step_ticket(context):
    assert context.ticket_id, "aucun ticket"
'''

_STEP_GIVEN_QUI_LEVE = '''
from behave import given

@given('le ticket est bien créé')
def step_ticket(context):
    if not context.ticket_id:
        raise AssertionError("aucun ticket")
'''


def _kinds(contenu):
    return [w["kind"] for w in lint_steps(contenu)]


def test_un_assert_sous_given_est_signale_au_relecteur():
    assert ASSERTION_DANS_CONTEXTE in _kinds(_STEP_GIVEN_AVEC_ASSERT)
    assert ASSERTION_DANS_CONTEXTE in _kinds(_STEP_GIVEN_QUI_LEVE)
    message = next(w["message"] for w in lint_steps(_STEP_GIVEN_AVEC_ASSERT)
                   if w["kind"] == ASSERTION_DANS_CONTEXTE)
    assert "bloqué" in message and "@then" in message


def test_un_step_given_d_action_ou_un_then_ne_sont_pas_signales():
    action = '''
from behave import given

@given('je renseigne le champ "{f}"')
def step_champ(context, f):
    context.page.fill(f, "x")
'''
    constat = '''
from behave import then

@then('le ticket est bien créé')
def step_ticket(context):
    assert context.ticket_id
'''
    double = '''
from behave import given, then

@given('le ticket est bien créé')
@then('le ticket est bien créé')
def step_ticket(context):
    assert context.ticket_id
'''
    assert ASSERTION_DANS_CONTEXTE not in _kinds(action)
    assert ASSERTION_DANS_CONTEXTE not in _kinds(constat)
    assert ASSERTION_DANS_CONTEXTE not in _kinds(double), "un step aussi @then reste un constat"


def test_le_gate_connait_la_famille_de_ce_nouvel_avertissement():
    source = (RACINE / "frontend" / "src" / "components" / "ReviewGate.vue").read_text(encoding="utf-8")

    assert "assertion_dans_contexte: 'assertion'" in source


# ── 3. Migration 48 : un saut est journalisé ─────────────────────────────────────────────────

def test_une_table_non_reconnue_est_sautee_MAIS_journalisee(tmp_path, caplog):
    conn = sqlite3.connect(str(tmp_path / "x.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY, "
                 "execution_status TEXT CHECK (execution_status IN ('a','b')))")
    conn.commit()

    with caplog.at_level(logging.WARNING, logger="testpilot.store.db"):
        _migrate_48_execution_blocked(conn)

    assert any("execution non reconnue" in r.getMessage() and "NON migrée" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
    conn.close()


def test_une_table_absente_ou_deja_migree_n_est_pas_un_avertissement(tmp_path, caplog):
    conn = sqlite3.connect(str(tmp_path / "vide.db"))
    conn.row_factory = sqlite3.Row

    with caplog.at_level(logging.WARNING, logger="testpilot.store.db"):
        _migrate_48_execution_blocked(conn)  # aucune des trois tables n'existe

    assert not [r for r in caplog.records if "migration 48" in r.getMessage()]
    conn.close()


# ── 4. Alembic : montée et descente ──────────────────────────────────────────────────────────

def _alembic(tmp_path, monkeypatch):
    from alembic.config import Config

    from testpilot import config

    chemin = tmp_path / "alembic.db"
    cfg = Config(str(RACINE / "alembic.ini"))
    monkeypatch.setattr(config, "DB_PATH", chemin, raising=False)
    monkeypatch.setenv("TESTPILOT_DB_URL", f"sqlite:///{chemin.as_posix()}")
    return cfg, chemin


def _sql(chemin, table):
    conn = sqlite3.connect(str(chemin))
    try:
        return conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
    finally:
        conn.close()


def _inserer_ligne_minimale(conn, table, **valeurs):
    """Remplit les colonnes NOT NULL sans défaut avec un placeholder de leur type."""
    colonnes = conn.execute(f"PRAGMA table_info({table})").fetchall()
    ligne = dict(valeurs)
    for c in colonnes:
        nom, type_, non_nul, defaut = c[1], (c[2] or "").upper(), c[3], c[4]
        if nom in ligne or c[5] or not non_nul or defaut is not None:
            continue
        ligne[nom] = 0 if any(t in type_ for t in ("INT", "REAL", "NUM")) else "x"
    noms = ", ".join(ligne)
    conn.execute(f"INSERT INTO {table} ({noms}) VALUES ({', '.join('?' for _ in ligne)})",
                 tuple(ligne.values()))


def test_alembic_head_accepte_blocked_et_le_downgrade_le_convertit_en_technical_error(
        tmp_path, monkeypatch):
    from alembic import command

    cfg, chemin = _alembic(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    for table in ("execution", "test_case", "scenario_result"):
        assert "'blocked'" in _sql(chemin, table), f"{table} : le head doit accepter `blocked`"

    conn = sqlite3.connect(str(chemin))
    conn.execute("PRAGMA foreign_keys = OFF")
    _inserer_ligne_minimale(conn, "execution", execution_status="blocked")
    try:
        _inserer_ligne_minimale(conn, "execution", execution_status="bidon")
        refuse = False
    except sqlite3.IntegrityError:
        refuse = True
    conn.commit()
    conn.close()
    assert refuse, "une valeur inconnue reste refusée par le CHECK"

    command.downgrade(cfg, "c47f22092026")

    for table in ("execution", "test_case", "scenario_result"):
        assert "'blocked'" not in _sql(chemin, table), f"{table} : le downgrade retire `blocked`"
    conn = sqlite3.connect(str(chemin))
    statuts = [r[0] for r in conn.execute("SELECT execution_status FROM execution")]
    conn.close()
    assert statuts == ["technical_error"], "la ligne `blocked` redevient ce qu'elle était avant le lot"

    command.upgrade(cfg, "head")
    assert "'blocked'" in _sql(chemin, "execution")
