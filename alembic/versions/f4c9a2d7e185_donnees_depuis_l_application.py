"""Données de test depuis l'application et lignes d'un cas à relire (étape 6 du plan unique : IT-4, A55 ; IT-3d, A58 point 5).

Revision ID: f4c9a2d7e185
Revises: e8a4c2f6b913

Colonnes `test_variable.source_application` (d'où une colonne tire ses valeurs à chaque lancement : des enregistrements qui
existent dans l'application ; vide = valeurs saisies) et `test_case.lignes_ecrites_pour` (empreinte du texte du cas quand ses
lignes ont été enregistrées ; vide = lignes d'avant). Même évolution que la migration SQLite 75 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "f4c9a2d7e185"
down_revision = "e8a4c2f6b913"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_variable") as batch_op:
        batch_op.add_column(sa.Column("source_application", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("test_case") as batch_op:
        batch_op.add_column(sa.Column("lignes_ecrites_pour", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("test_case") as batch_op:
        batch_op.drop_column("lignes_ecrites_pour")
    with op.batch_alter_table("test_variable") as batch_op:
        batch_op.drop_column("source_application")
