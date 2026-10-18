"""Itérations : le résultat de chaque itération (décision A52 du porteur, 2026-10-16).

Revision ID: b3e7c9d1f405
Revises: a8d3f5c1e264

`scenario_result.iterations` : les numéros des itérations que ce scénario couvre (« 1,3 », 1 = la première ligne) ; vide =
toutes.
Même évolution que la migration SQLite 71 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "b3e7c9d1f405"
down_revision = "a8d3f5c1e264"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("scenario_result") as batch_op:
        batch_op.add_column(sa.Column("iterations", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("scenario_result") as batch_op:
        batch_op.drop_column("iterations")
