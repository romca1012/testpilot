"""Adresse de remise à zéro du bac à sable (décision D26, lot VH-07).

Revision ID: d1a7b3c5e924
Revises: c9f4a2d6e813

`project.bac_a_sable_reset` : avec la calibration en écriture, déclare que l'application du projet est un bac à sable sur lequel
l'agent peut jouer ses actions pendant la génération, remis à zéro avant et après chaque essai. Vide par défaut. Même évolution
que la migration SQLite 61 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "d1a7b3c5e924"
down_revision = "c9f4a2d6e813"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("bac_a_sable_reset", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("bac_a_sable_reset")
