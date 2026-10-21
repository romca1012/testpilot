"""Le compte avec lequel une ligne de données du cas est jouée (décisions A90-A92 du porteur, 2026-10-21 — étape 4).

Revision ID: e8a4c2f6b913
Revises: d7e3b9a1c642

Colonnes `case_data_row.compte_choisi` (0 : la ligne reprend « Joué en tant que » du cas ; 1 : `compte_id` est son compte,
NULL = le principal) et `case_data_row.compte_id`. Sans clé étrangère à suppression automatique : un compte supprimé bloque le
test, jamais un repli silencieux sur le principal. Même évolution que la migration SQLite 74 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "e8a4c2f6b913"
down_revision = "d7e3b9a1c642"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("case_data_row") as batch_op:
        batch_op.add_column(sa.Column("compte_choisi", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("compte_id", sa.Integer(), nullable=True))
        batch_op.create_check_constraint("ck_case_data_row_compte_choisi", "compte_choisi IN (0, 1)")


def downgrade():
    with op.batch_alter_table("case_data_row") as batch_op:
        batch_op.drop_constraint("ck_case_data_row_compte_choisi", type_="check")
        batch_op.drop_column("compte_id")
        batch_op.drop_column("compte_choisi")
