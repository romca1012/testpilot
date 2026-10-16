"""Environnements d'un projet (paramètres de test, lot PT-04a, décisions A48 à A50 du porteur, 2026-10-16).

Revision ID: f6c1d8a2e937
Revises: e4b8c2f19a63

Table `project_environment` (les environnements AJOUTÉS : nom, adresse, version, base, oracle, nature Test/Production) ;
`project.environnement_nom` (le nom de l'environnement par défaut, qui reste l'adresse du projet) ; `test_run.environment_id`
et `test_run.environnement_fige` (l'environnement choisi et ses valeurs figées au lancement) ; `scheduled_run.environment_ids`.
Même évolution que la migration SQLite 69 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "f6c1d8a2e937"
down_revision = "e4b8c2f19a63"
branch_labels = None
depends_on = None

_VIVANT = sa.text("deleted_at = ''")


def upgrade():
    op.create_table(
        "project_environment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("connector_version", sa.Text(), nullable=False, server_default=""),
        sa.Column("database", sa.Text(), nullable=False, server_default=""),
        sa.Column("oracle_base_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("nature", sa.Text(), nullable=False),
        sa.Column("rang", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("deleted_by", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint("nature IN ('test', 'production')", name="ck_project_environment_nature"),
        sqlite_autoincrement=True,
    )
    op.create_index("uq_project_environment_nom", "project_environment", ["project_id", "nom"], unique=True,
                    sqlite_where=_VIVANT, postgresql_where=_VIVANT)
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("environnement_nom", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.add_column(sa.Column("environment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("environnement_fige", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("scheduled_run") as batch_op:
        batch_op.add_column(sa.Column("environment_ids", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("scheduled_run") as batch_op:
        batch_op.drop_column("environment_ids")
    with op.batch_alter_table("test_run") as batch_op:
        batch_op.drop_column("environnement_fige")
        batch_op.drop_column("environment_id")
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("environnement_nom")
    op.drop_index("uq_project_environment_nom", table_name="project_environment")
    op.drop_table("project_environment")
