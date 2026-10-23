"""Fiches de calcul des valeurs attendues (étape 7 du plan unique, décisions A108 et A110 du porteur, 2026-10-23).

Revision ID: b8e2f4a6c193
Revises: a7d3e9b2c418

Table `fiche_de_calcul` (propre à un projet et à un cas ; origine `ia` ou `personne` ; statut `proposee`, `retenue` — choisie
par une personne, vaut validation — ou `ecartee`) ; colonne `test_case.calcul_detecte` (pourquoi le cas attend une valeur
calculée ; vide = rien de détecté). Même évolution que la migration SQLite 77 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "b8e2f4a6c193"
down_revision = "a7d3e9b2c418"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fiche_de_calcul",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.Text(), nullable=False),
        sa.Column("contenu", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("origine", sa.Text(), nullable=False),
        sa.Column("statut", sa.Text(), nullable=False, server_default="proposee"),
        sa.Column("auteur", sa.Text(), nullable=False, server_default=""),
        sa.Column("retenue_par", sa.Text(), nullable=False, server_default=""),
        sa.Column("retenue_le", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("origine IN ('ia', 'personne')", name="ck_fiche_de_calcul_origine"),
        sa.CheckConstraint("statut IN ('proposee', 'retenue', 'ecartee')", name="ck_fiche_de_calcul_statut"),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_fiche_de_calcul_case", "fiche_de_calcul", ["case_id"])
    with op.batch_alter_table("test_case") as batch_op:
        batch_op.add_column(sa.Column("calcul_detecte", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("test_case") as batch_op:
        batch_op.drop_column("calcul_detecte")
    op.drop_index("idx_fiche_de_calcul_case", table_name="fiche_de_calcul")
    op.drop_table("fiche_de_calcul")
