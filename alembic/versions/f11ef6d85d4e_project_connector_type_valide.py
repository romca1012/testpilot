"""project.connector_type gagne un CHECK ('odoo', 'web').

Revision ID: f11ef6d85d4e
Revises: 41fbce28312f
"""
from alembic import op

revision = "f11ef6d85d4e"
down_revision = "41fbce28312f"
branch_labels = None
depends_on = None


def upgrade():
    # Normalisation AVANT le CHECK : préserve le comportement déjà en vigueur pour toute ligne
    # existante (`connectors/factory.py::build_connector` la traite déjà comme générique) plutôt
    # que de faire échouer la contrainte sur une donnée que rien n'a jamais rejetée jusqu'ici.
    op.execute("UPDATE project SET connector_type = 'web' "
              "WHERE connector_type NOT IN ('odoo', 'web')")
    # `batch_alter_table` : SQLite ne sait pas ajouter un CHECK par un simple ALTER (il exige la
    # stratégie copie-et-bascule que le mode batch fournit) ; Postgres, cible réelle de ce fichier,
    # accepte le même appel sans reconstruction.
    with op.batch_alter_table("project") as batch_op:
        batch_op.create_check_constraint(
            "ck_project_connector_type", "connector_type IN ('odoo', 'web')")


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_constraint("ck_project_connector_type", type_="check")
