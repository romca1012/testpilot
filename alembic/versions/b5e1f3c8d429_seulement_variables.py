"""Une exécution qui ne joue que les tests écrivant des variables (paramètres de test, lot PT-02b, décision A35).

Revision ID: b5e1f3c8d429
Revises: a4d9e2b7c318

Colonne `test_run.seulement_variables` (0/1). Même évolution que la migration SQLite 65 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "b5e1f3c8d429"
down_revision = "a4d9e2b7c318"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("seulement_variables", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_check_constraint("ck_test_run_seulement_variables", "seulement_variables IN (0, 1)")


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_constraint("ck_test_run_seulement_variables", type_="check")
        batch_op.drop_column("seulement_variables")
