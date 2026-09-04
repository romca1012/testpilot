"""Ajoute la file durable des traitements de fond.

Revision ID: f83b5c7d1e42
Revises: e72a4b6c9d10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f83b5c7d1e42"
down_revision: str | Sequence[str] | None = "e72a4b6c9d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_job",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("queue_label", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("finished_at", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_background_job_status",
        ),
    )
    op.create_index(
        "idx_background_job_status_created", "background_job", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_background_job_status_created", table_name="background_job")
    op.drop_table("background_job")
