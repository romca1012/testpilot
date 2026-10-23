"""Plage des lignes propres aux cas, choisie au lancement d'une campagne automatique (porteur, 2026-10-23, A107).

Revision ID: a7d3e9b2c418
Revises: f4c9a2d7e185

Colonnes `test_run.ligne_debut` et `test_run.ligne_fin` : « de la ligne X à la ligne Y » (1 = la première ligne du cas) ; les
deux NULL = pas de plage (« toutes » ou « premiere », comme avant). Même évolution que la migration SQLite 76 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d3e9b2c418"
down_revision = "f4c9a2d7e185"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("ligne_debut", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ligne_fin", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_test_run_plage_des_lignes",
            "(ligne_debut IS NULL AND ligne_fin IS NULL) OR (ligne_debut >= 1 AND ligne_fin >= ligne_debut"
            " AND lignes_des_cas = 'toutes')")


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_constraint("ck_test_run_plage_des_lignes", type_="check")
        batch_op.drop_column("ligne_fin")
        batch_op.drop_column("ligne_debut")
