"""Plans de test (regroupement de campagnes) et planifications récurrentes.

Revision ID: 41fbce28312f
Revises: a94c6d8e2f53
"""
import sqlalchemy as sa
from alembic import op

revision = "41fbce28312f"
down_revision = "a94c6d8e2f53"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_plan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("refs", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_plan_project", "test_plan", ["project_id"])

    op.create_table(
        "scheduled_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("selection_mode", sa.Text(), nullable=False, server_default="frozen"),
        sa.Column("frequency", sa.Text(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_run_id", sa.Integer(), nullable=True),
        sa.Column("last_triggered_at", sa.Text(), nullable=True),
        sa.CheckConstraint("selection_mode IN ('all', 'frozen')",
                            name="ck_scheduled_run_selection_mode"),
        sa.CheckConstraint("frequency IN ('daily', 'weekly')", name="ck_scheduled_run_frequency"),
        sa.CheckConstraint("hour BETWEEN 0 AND 23", name="ck_scheduled_run_hour"),
        sa.CheckConstraint("minute BETWEEN 0 AND 59", name="ck_scheduled_run_minute"),
        sa.CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6",
                            name="ck_scheduled_run_weekday"),
    )
    op.create_index("idx_scheduled_run_project", "scheduled_run", ["project_id"])
    op.create_index("idx_scheduled_run_active", "scheduled_run", ["is_active"])

    op.create_table(
        "scheduled_run_case",
        sa.Column("scheduled_run_id", sa.Integer(), sa.ForeignKey("scheduled_run.id"),
                  nullable=False, primary_key=True),
        sa.Column("case_id", sa.Integer(), nullable=False, primary_key=True),
    )


def downgrade():
    op.drop_table("scheduled_run_case")
    op.drop_index("idx_scheduled_run_active", table_name="scheduled_run")
    op.drop_index("idx_scheduled_run_project", table_name="scheduled_run")
    op.drop_table("scheduled_run")
    op.drop_index("idx_plan_project", table_name="test_plan")
    op.drop_table("test_plan")
