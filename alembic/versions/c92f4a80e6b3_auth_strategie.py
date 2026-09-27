"""Strategie de connexion du compte principal d'un projet (lot 07b-2, C2).

Revision ID: c92f4a80e6b3
Revises: a51c7e2d9b04

`project.auth_strategie` (CHECK), `totp_secret`, `injected_session` (chiffres) : vide/formulaire = comportement actuel.
"""
import sqlalchemy as sa
from alembic import op

revision = "c92f4a80e6b3"
down_revision = "a51c7e2d9b04"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("auth_strategie", sa.Text(), nullable=False, server_default="formulaire"))
        batch_op.add_column(sa.Column("totp_secret", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("injected_session", sa.Text(), nullable=False, server_default=""))
        batch_op.create_check_constraint(
            "ck_project_auth_strategie", "auth_strategie IN ('formulaire', 'totp', 'session_injectee', 'aucune')")


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_constraint("ck_project_auth_strategie", type_="check")
        batch_op.drop_column("injected_session")
        batch_op.drop_column("totp_secret")
        batch_op.drop_column("auth_strategie")
