"""Persiste le compteur anti-brute-force.

Revision ID: e72a4b6c9d10
Revises: d91f5c3a7e20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e72a4b6c9d10"
down_revision: str | Sequence[str] | None = "d91f5c3a7e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_failure",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("attempt_key", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "idx_login_failure_key_time", "login_failure", ["attempt_key", "occurred_at"])


def downgrade() -> None:
    op.drop_index("idx_login_failure_key_time", table_name="login_failure")
    op.drop_table("login_failure")
