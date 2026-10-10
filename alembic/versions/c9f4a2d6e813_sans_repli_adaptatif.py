"""Campagne sans repli par le modèle de langage (décision D33, prolonge D25).

Revision ID: c9f4a2d6e813
Revises: b7e3c1a9d405

`test_run.sans_repli` : la campagne se joue sans résolution adaptative (LLM) à l'exécution, en gardant second essai et
réparation. Vrai par défaut, campagnes existantes comprises. Même évolution que la migration SQLite 60 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "c9f4a2d6e813"
down_revision = "b7e3c1a9d405"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("sans_repli", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_check_constraint("ck_test_run_sans_repli", "sans_repli IN (0, 1)")


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_constraint("ck_test_run_sans_repli", type_="check")
        batch_op.drop_column("sans_repli")
