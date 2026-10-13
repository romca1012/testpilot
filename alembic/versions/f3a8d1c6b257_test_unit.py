"""Unités ajoutées par un projet (paramètres de test, lot PT-03).

Revision ID: f3a8d1c6b257
Revises: e7c2f4a9b136

Table `test_unit` : une unité déclarée par un projet et ses autres écritures. `project_id` nullable dès la création (NULL =
bibliothèque commune, lot PT-05). Même évolution que la migration SQLite 63 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a8d1c6b257"
down_revision = "e7c2f4a9b136"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_unit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("nom", sa.Text(), nullable=False),
        sa.Column("ecritures", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "nom", name="uq_test_unit_nom"),
        sqlite_autoincrement=True,
    )


def downgrade():
    op.drop_table("test_unit")
