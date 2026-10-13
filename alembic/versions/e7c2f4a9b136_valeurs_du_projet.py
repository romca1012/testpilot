"""Monnaie et écriture des nombres d'un projet (paramètres de test, lot PT-03, décisions A8 et A24).

Revision ID: e7c2f4a9b136
Revises: d1a7b3c5e924

`project.devise` (code ISO 4217) et `project.format_nombre` (`espace_virgule`, `virgule_point` ou `point_virgule` ; CHECK) :
vide = rien de déclaré, rien ne change pour un projet existant. Même évolution que la migration SQLite 62 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "e7c2f4a9b136"
down_revision = "d1a7b3c5e924"
branch_labels = None
depends_on = None

_COLONNES = ("devise", "format_nombre")
_CONTRAINTE = "format_nombre IN ('', 'espace_virgule', 'virgule_point', 'point_virgule')"


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        for colonne in _COLONNES:
            batch_op.add_column(sa.Column(colonne, sa.Text(), nullable=False, server_default=""))
        batch_op.create_check_constraint("ck_project_format_nombre", _CONTRAINTE)


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_constraint("ck_project_format_nombre", type_="check")
        for colonne in reversed(_COLONNES):
            batch_op.drop_column(colonne)
