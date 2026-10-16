"""« L'IA peut agir sur cette application » allumé par défaut (décision A43 du porteur, 2026-10-16).

Revision ID: d9e3a1b7c582
Revises: c7a2e9d4f610

`project.calibration_writes_enabled` : défaut 1, et les projets existants sont cochés (sauf un refus délibéré : remise
à zéro déclarée et case décochée). Même évolution que la migration
SQLite 67 (`store/db.py`).
"""
import sqlalchemy as sa
from alembic import op

revision = "d9e3a1b7c582"
down_revision = "c7a2e9d4f610"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project") as batch_op:
        batch_op.alter_column("calibration_writes_enabled", existing_type=sa.Integer(), server_default="1")
    # A45 : un projet qui avait déclaré une remise à zéro et laissé la case décochée l'a refusée exprès — pas recoché.
    op.execute("UPDATE project SET calibration_writes_enabled = 1 "
               "WHERE calibration_writes_enabled = 0 AND bac_a_sable_reset = ''")


def downgrade():
    # Le défaut redevient 0 ; les projets cochés par l'upgrade le restent (on ne sait plus lesquels l'étaient avant).
    with op.batch_alter_table("project") as batch_op:
        batch_op.alter_column("calibration_writes_enabled", existing_type=sa.Integer(), server_default="0")
