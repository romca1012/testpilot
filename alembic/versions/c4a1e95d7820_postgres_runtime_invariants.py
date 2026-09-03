"""Rétablit sous PostgreSQL les invariants auparavant assurés par SQLite.

Revision ID: c4a1e95d7820
Revises: b7d91c21f638
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4a1e95d7820"
down_revision: str | Sequence[str] | None = "b7d91c21f638"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INDEXES = (
    ("uq_project_name", "project", "lower(name)", "deleted_at = ''"),
    ("uq_module_project_name", "module", "project_id, lower(name)", "deleted_at = ''"),
    ("uq_group_module_title", "case_group", "module_id, lower(title)", "deleted_at = ''"),
    ("uq_case_group_title", "test_case", "group_id, lower(title)", "deleted_at = ''"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for nom, table, expression, filtre in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{nom}"')
        op.execute(
            f'CREATE UNIQUE INDEX "{nom}" ON "{table}" ({expression}) WHERE {filtre}')

    op.execute("""
        CREATE OR REPLACE FUNCTION testpilot_verifier_mode_resultat()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.mode IS DISTINCT FROM (SELECT mode FROM test_run WHERE id = NEW.run_id) THEN
                RAISE EXCEPTION 'le mode du résultat ne concorde pas avec celui de sa campagne'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_resultat_suit_le_mode_de_sa_campagne
        BEFORE INSERT OR UPDATE OF mode, run_id ON test_result
        FOR EACH ROW EXECUTE FUNCTION testpilot_verifier_mode_resultat()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_resultat_suit_le_mode_de_sa_campagne ON test_result")
    op.execute("DROP FUNCTION IF EXISTS testpilot_verifier_mode_resultat()")
    for nom, table, _, filtre in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{nom}"')
    op.execute("CREATE UNIQUE INDEX uq_project_name ON project (name) WHERE deleted_at = ''")
    op.execute("CREATE UNIQUE INDEX uq_module_project_name ON module (project_id, name) "
               "WHERE deleted_at = ''")
    op.execute("CREATE UNIQUE INDEX uq_group_module_title ON case_group (module_id, title) "
               "WHERE deleted_at = ''")
    op.execute("CREATE UNIQUE INDEX uq_case_group_title ON test_case (group_id, title) "
               "WHERE deleted_at = ''")
