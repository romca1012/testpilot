"""Parcours d'un cas enregistrés dans le navigateur en direct (étape 7b du plan unique, décision A109 du porteur, 2026-10-23).

Revision ID: c3f7a9d2e481
Revises: b8e2f4a6c193

Table `parcours_enregistre` (rattachée au cas, gardée dans l'historique ; actions et éléments à vérifier en JSON ; `version_id`
de la version de test écrite à partir de lui) ; colonne `live_session_token.case_id` (le cas d'une session d'enregistrement de
parcours ; NULL : enregistrement de la connexion). Même évolution que la migration SQLite 78 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "c3f7a9d2e481"
down_revision = "b8e2f4a6c193"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parcours_enregistre",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("actions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("auteur", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_parcours_enregistre_case", "parcours_enregistre", ["case_id"])
    with op.batch_alter_table("live_session_token") as batch_op:
        batch_op.add_column(sa.Column("case_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("live_session_token") as batch_op:
        batch_op.drop_column("case_id")
    op.drop_index("idx_parcours_enregistre_case", table_name="parcours_enregistre")
    op.drop_table("parcours_enregistre")
