"""Inspections conservées avec la version : le crawl omet le back-office Parc IT."""
import sqlalchemy as sa

from alembic import op

revision = "b46f18092026"
down_revision = "a3f7c9e1b204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_case_version", sa.Column("verified_fields", sa.Text(),
                                              nullable=False, server_default=""))


def downgrade():
    op.drop_column("test_case_version", "verified_fields")
