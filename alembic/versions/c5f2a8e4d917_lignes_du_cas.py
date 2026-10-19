"""Lignes propres à un cas : ses classes de valeurs, jouées en itérations (décisions A57 et A58 du porteur, 2026-10-19).

Revision ID: c5f2a8e4d917
Revises: b3e7c9d1f405

Tables `case_data_row` et `case_data_value` ; colonne `test_run.lignes_des_cas` (« toutes » ou « premiere »). Même évolution
que la migration SQLite 72 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "c5f2a8e4d917"
down_revision = "b3e7c9d1f405"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_data_row",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.Text(), nullable=False, server_default=""),
        sa.Column("rang", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_case_data_row_case", "case_data_row", ["case_id"])
    op.create_table(
        "case_data_value",
        sa.Column("row_id", sa.Integer(), sa.ForeignKey("case_data_row.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variable_id", sa.Integer(), sa.ForeignKey("test_variable.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valeur", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("row_id", "variable_id"),
    )
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("lignes_des_cas", sa.Text(), nullable=False, server_default="toutes"))
        batch_op.create_check_constraint("ck_test_run_lignes_des_cas", "lignes_des_cas IN ('toutes', 'premiere')")


def downgrade():
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_constraint("ck_test_run_lignes_des_cas", type_="check")
        batch_op.drop_column("lignes_des_cas")
    op.drop_table("case_data_value")
    op.drop_index("idx_case_data_row_case", table_name="case_data_row")
    op.drop_table("case_data_row")
