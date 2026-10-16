"""`project.instance_de_test` — un projet Odoo se déclare instance de test (décision A45 du porteur, 2026-10-16).

Revision ID: e4b8c2f19a63
Revises: d9e3a1b7c582

Éteint par défaut : sans cette déclaration, l'IA n'écrit jamais dans une application Odoo pendant la génération, même si
« L'IA peut agir » est coché. Même évolution que la migration SQLite 68 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "e4b8c2f19a63"
down_revision = "d9e3a1b7c582"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("instance_de_test", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("instance_de_test")
