"""project.calibration_writes_enabled — calibration en écriture pendant la génération, éteinte
par défaut (migration 45).

Revision ID: a3f7c9e1b204
Revises: f11ef6d85d4e
"""
from alembic import op
import sqlalchemy as sa

revision = "a3f7c9e1b204"
down_revision = "f11ef6d85d4e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column("calibration_writes_enabled", sa.Integer(), nullable=False,
                     server_default="0"))


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("calibration_writes_enabled")
