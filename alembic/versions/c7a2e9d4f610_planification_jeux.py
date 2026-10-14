"""Les jeux de données d'une planification (paramètres de test, lot PT-02b, décision A28).

Revision ID: c7a2e9d4f610
Revises: b5e1f3c8d429

Colonne `scheduled_run.dataset_ids` (liste JSON d'ids, vide par défaut). Même évolution que la migration SQLite 66
(`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "c7a2e9d4f610"
down_revision = "b5e1f3c8d429"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("scheduled_run") as batch_op:
        batch_op.add_column(sa.Column("dataset_ids", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("scheduled_run") as batch_op:
        batch_op.drop_column("dataset_ids")
