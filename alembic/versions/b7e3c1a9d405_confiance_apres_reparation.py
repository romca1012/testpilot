"""Confiance « après réparation » (lot VH-03, décision D28).

Revision ID: b7e3c1a9d405
Revises: 05cd83825e18

`execution.confiance` accepte `apres_reparation` : le résultat d'une version RÉPARÉE par l'agent et pas encore relue n'est ni
« nominal » ni le résultat du cas. Même évolution que la migration SQLite 59 (`store/db.py`).
"""
from alembic import op

revision = "b7e3c1a9d405"
down_revision = "05cd83825e18"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("execution") as batch_op:
        batch_op.drop_constraint("ck_execution_confiance", type_="check")
        batch_op.create_check_constraint(
            "ck_execution_confiance", "confiance IN ('nominale', 'auto_resolue', 'apres_retry', 'apres_reparation')")


def downgrade():
    op.execute("UPDATE execution SET confiance='nominale' WHERE confiance='apres_reparation'")
    with op.batch_alter_table("execution") as batch_op:
        batch_op.drop_constraint("ck_execution_confiance", type_="check")
        batch_op.create_check_constraint(
            "ck_execution_confiance", "confiance IN ('nominale', 'auto_resolue', 'apres_retry')")
