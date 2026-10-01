"""F26(b) : dépendance inter-cas déclarée par le métier (lot 10).

Revision ID: 05cd83825e18
Revises: d6e29a4f8c31

`test_case_version.depend_dun_autre_cas_du_groupe` (CHECK 0/1) et `etat_a_creer_par_ce_cas` :
persistent ce que `metier_writer.MetierDraft` calcule déjà, pour que `tools/write.py` puisse le
relire au moment de la génération du Gherkin (round-trip relecture → automatisation, cf. migration
58 de `db.py` pour le détail du besoin).
"""
import sqlalchemy as sa
from alembic import op

revision = "05cd83825e18"
down_revision = "d6e29a4f8c31"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_case_version") as batch_op:
        batch_op.add_column(sa.Column("depend_dun_autre_cas_du_groupe", sa.Integer(),
                                      nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("etat_a_creer_par_ce_cas", sa.Text(),
                                      nullable=False, server_default=""))
        batch_op.create_check_constraint(
            "ck_test_case_version_depend_dun_autre_cas_du_groupe",
            "depend_dun_autre_cas_du_groupe IN (0, 1)")


def downgrade():
    with op.batch_alter_table("test_case_version") as batch_op:
        batch_op.drop_constraint("ck_test_case_version_depend_dun_autre_cas_du_groupe", type_="check")
        batch_op.drop_column("etat_a_creer_par_ce_cas")
        batch_op.drop_column("depend_dun_autre_cas_du_groupe")
