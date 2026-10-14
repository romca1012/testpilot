"""Données de test d'un projet : variables, jeux de données, valeurs figées (paramètres de test, lot PT-02).

Revision ID: a4d9e2b7c318
Revises: f3a8d1c6b257

Tables `test_variable`, `test_dataset`, `test_dataset_value` ; colonnes `test_run.dataset_id`, `test_run.parametres_figes`,
`execution.parametres_joues`. Même évolution que la migration SQLite 64 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "a4d9e2b7c318"
down_revision = "f3a8d1c6b257"
branch_labels = None
depends_on = None

_VIVANT = sa.text("deleted_at = ''")


def upgrade():
    for table, propre in (("test_variable", sa.Column("description", sa.Text(), nullable=False, server_default="")),
                          ("test_dataset", sa.Column("est_defaut", sa.Integer(), nullable=False, server_default="0"))):
        contraintes = [sa.CheckConstraint("est_defaut IN (0, 1)", name="ck_test_dataset_est_defaut")] if table == "test_dataset" else []
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
            sa.Column("nom", sa.Text(), nullable=False),
            propre,
            sa.Column("rang", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("deleted_at", sa.Text(), nullable=False, server_default=""),
            sa.Column("deleted_by", sa.Text(), nullable=False, server_default=""),
            *contraintes,
            sqlite_autoincrement=True,
        )
        op.create_index(f"uq_{table}_nom", table, ["project_id", "nom"], unique=True,
                        sqlite_where=_VIVANT, postgresql_where=_VIVANT)
    op.create_table(
        "test_dataset_value",
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("test_dataset.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variable_id", sa.Integer(), sa.ForeignKey("test_variable.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valeur", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("dataset_id", "variable_id"),
    )
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("dataset_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parametres_figes", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("execution") as batch_op:
        batch_op.add_column(sa.Column("parametres_joues", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("execution") as batch_op:
        batch_op.drop_column("parametres_joues")
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_column("parametres_figes")
        batch_op.drop_column("dataset_id")
    op.drop_table("test_dataset_value")
    for table in ("test_dataset", "test_variable"):
        op.drop_index(f"uq_{table}_nom", table_name=table)
        op.drop_table(table)
