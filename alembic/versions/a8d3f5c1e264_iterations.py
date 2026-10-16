"""Itérations : les lignes de données de test d'une exécution (décision A52 du porteur, 2026-10-16).

Revision ID: a8d3f5c1e264
Revises: f6c1d8a2e937

`test_run.dataset_ids` : les jeux de données (lignes) joués par une exécution, une itération par ligne (liste JSON) ; vide =
comme avant (`dataset_id`, un seul jeu). Même évolution que la migration SQLite 70 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "a8d3f5c1e264"
down_revision = "f6c1d8a2e937"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("dataset_ids", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_column("dataset_ids")
