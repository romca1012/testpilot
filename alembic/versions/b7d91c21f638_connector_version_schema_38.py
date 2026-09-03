"""Ajoute la version déclarée du connecteur (alignement schéma SQLite 38).

Revision ID: b7d91c21f638
Revises: adc3e4b5c1bb
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d91c21f638"
down_revision: str | Sequence[str] | None = "adc3e4b5c1bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project", sa.Column("connector_version", sa.Text(),
                                       nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("project", "connector_version")
