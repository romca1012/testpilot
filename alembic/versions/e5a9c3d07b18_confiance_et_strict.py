"""Confiance du verdict et campagne stricte (lot 05, décision D5).

Revision ID: e5a9c3d07b18
Revises: d48b7e2c0926

`execution.confiance` : comment le verdict a été obtenu (`nominale`, `auto_resolue`, `apres_retry`). L'HISTORIQUE reçoit
`nominale` par défaut — ce n'est pas une mesure, la confiance n'était pas calculée avant ce lot.
`test_run.strict` : la campagne se joue sans résolution adaptative ni retry.
"""
import sqlalchemy as sa
from alembic import op

revision = "e5a9c3d07b18"
down_revision = "d48b7e2c0926"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("execution") as batch_op:
        batch_op.add_column(sa.Column("confiance", sa.Text(), nullable=False, server_default="nominale"))
        batch_op.create_check_constraint(
            "ck_execution_confiance", "confiance IN ('nominale', 'auto_resolue', 'apres_retry')")
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("strict", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_check_constraint("ck_test_run_strict", "strict IN (0, 1)")


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_constraint("ck_test_run_strict", type_="check")
        batch_op.drop_column("strict")
    with op.batch_alter_table("execution") as batch_op:
        batch_op.drop_constraint("ck_execution_confiance", type_="check")
        batch_op.drop_column("confiance")
