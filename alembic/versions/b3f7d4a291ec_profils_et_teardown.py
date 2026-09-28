"""Profils d'instance et residus de teardown (lot 06, D6, F6).

Revision ID: b3f7d4a291ec
Revises: c92f4a80e6b3

`project.profil_instance` (profil d'instance a inclure, vide = aucun) ;
`execution.residus` (JSON, informatif, meme motif que field_fallbacks).
"""
import sqlalchemy as sa
from alembic import op

revision = "b3f7d4a291ec"
down_revision = "c92f4a80e6b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("profil_instance", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("execution") as batch_op:
        batch_op.add_column(sa.Column("residus", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("execution") as batch_op:
        batch_op.drop_column("residus")
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("profil_instance")
