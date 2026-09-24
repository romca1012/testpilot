"""L'axe exécution accepte la valeur 'blocked' (lot 02, décision D1).

Revision ID: d48b7e2c0926
Revises: c47f22092026

Trois CHECK portent l'axe exécution : `execution`, `test_case.last_execution_status` et
`scenario_result`. Sans cette révision, un cas jugé `blocked` planterait à la persistance
(`IntegrityError`) — exactement le défaut que la migration SQLite 19 avait déjà mis au jour pour
`donnee_invalide`.
"""
from alembic import op

revision = "d48b7e2c0926"
down_revision = "c47f22092026"
branch_labels = None
depends_on = None

# (table, contrainte, colonne, valeurs AVANT ce lot)
_CHECKS = (
    ("execution", "ck_execution_execution_status", "execution_status",
     ("success", "technical_error", "not_executed")),
    ("test_case", "ck_test_case_last_execution_status", "last_execution_status",
     ("success", "technical_error", "not_executed")),
    ("scenario_result", "ck_scenario_result_execution_status", "execution_status",
     ("success", "technical_error")),
)


def _liste(valeurs) -> str:
    return ", ".join(f"'{v}'" for v in valeurs)


def upgrade():
    for table, nom, colonne, valeurs in _CHECKS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(nom, type_="check")
            batch_op.create_check_constraint(nom, f"{colonne} IN ({_liste((*valeurs, 'blocked'))})")


def downgrade():
    for table, nom, colonne, valeurs in _CHECKS:
        # Une ligne `blocked` n'existe pas dans l'ancien vocabulaire : elle redevient `technical_error`,
        # ce qu'elle était avant le lot 02 (le test n'avait pas pu tourner).
        op.execute(f"UPDATE {table} SET {colonne} = 'technical_error' WHERE {colonne} = 'blocked'")
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(nom, type_="check")
            batch_op.create_check_constraint(nom, f"{colonne} IN ({_liste(valeurs)})")
