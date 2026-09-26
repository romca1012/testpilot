"""Comptes secondaires d'un projet (lot 07b-1, D8).

Revision ID: a51c7e2d9b04
Revises: f60b4d8e1a53

Table `project_account` : le compte principal reste sur `project` ; celle-ci ne porte que les autres.
"""
import sqlalchemy as sa
from alembic import op

revision = "a51c7e2d9b04"
down_revision = "f60b4d8e1a53"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password", sa.Text(), nullable=False, server_default=""),
        sa.Column("business_role", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "label", name="uq_project_account_label"),
        sqlite_autoincrement=True,
    )


def downgrade():
    op.drop_table("project_account")
