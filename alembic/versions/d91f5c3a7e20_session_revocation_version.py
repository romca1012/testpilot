"""Ajoute une version révocable aux sessions utilisateur.

Revision ID: d91f5c3a7e20
Revises: c4a1e95d7820
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d91f5c3a7e20"
down_revision: str | Sequence[str] | None = "c4a1e95d7820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("user", "session_version")
