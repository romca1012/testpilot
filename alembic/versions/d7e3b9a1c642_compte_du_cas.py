"""Le compte avec lequel un cas est joué (décision A70 du porteur, 2026-10-20 — étape 4 du plan unique).

Revision ID: d7e3b9a1c642
Revises: c5f2a8e4d917

Colonne `test_case_version.compte_id` : le compte du projet (`project_account.id`) avec lequel CETTE version du cas est jouée ;
NULL = le compte principal. Sans clé étrangère à suppression automatique : un compte supprimé ne fait jamais rejouer le cas en
silence avec le principal — l'exécution le dit et bloque. Même évolution que la migration SQLite 73 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "d7e3b9a1c642"
down_revision = "c5f2a8e4d917"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_case_version") as batch_op:
        batch_op.add_column(sa.Column("compte_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("test_case_version") as batch_op:
        batch_op.drop_column("compte_id")
