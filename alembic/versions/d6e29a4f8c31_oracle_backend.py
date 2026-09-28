"""Oracle backend HTTP optionnel d'un projet (lot 07e, C5, D7).

Revision ID: d6e29a4f8c31
Revises: a2d47f9c8e15

`project.oracle_type` (CHECK), `oracle_base_url`, `oracle_auth` (chiffre), `oracle_queries` :
vide = aucun oracle, comportement inchange.
"""
import sqlalchemy as sa
from alembic import op

revision = "d6e29a4f8c31"
down_revision = "a2d47f9c8e15"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("oracle_type", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("oracle_base_url", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("oracle_auth", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("oracle_queries", sa.Text(), nullable=False, server_default="[]"))
        batch_op.create_check_constraint("ck_project_oracle_type", "oracle_type IN ('', 'http')")


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_constraint("ck_project_oracle_type", type_="check")
        batch_op.drop_column("oracle_queries")
        batch_op.drop_column("oracle_auth")
        batch_op.drop_column("oracle_base_url")
        batch_op.drop_column("oracle_type")
