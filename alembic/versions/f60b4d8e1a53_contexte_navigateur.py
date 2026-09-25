"""Contexte navigateur figé d'un projet (lot 07c, C3).

Revision ID: f60b4d8e1a53
Revises: e5a9c3d07b18

`project.browser_locale`, `browser_timezone`, `browser_viewport` : vide = le défaut (fr-FR, Europe/Paris, 1440x900).
"""
import sqlalchemy as sa
from alembic import op

revision = "f60b4d8e1a53"
down_revision = "e5a9c3d07b18"
branch_labels = None
depends_on = None

_COLONNES = ("browser_locale", "browser_timezone", "browser_viewport")


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        for colonne in _COLONNES:
            batch_op.add_column(sa.Column(colonne, sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        for colonne in reversed(_COLONNES):
            batch_op.drop_column(colonne)
