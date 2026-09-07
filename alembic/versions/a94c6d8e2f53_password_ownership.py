"""Appropriation obligatoire des mots de passe existants et temporaires."""
import time
import sqlalchemy as sa
from alembic import op

revision = "a94c6d8e2f53"
down_revision = "f83b5c7d1e42"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("must_change_password", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user", sa.Column("password_expires_at", sa.Integer(), nullable=False, server_default="0"))
    op.execute(sa.text('UPDATE "user" SET must_change_password=1, password_expires_at=:expiry, '
                       'session_version=session_version+1').bindparams(expiry=int(time.time()) + 7 * 86400))
    # Fige l'accès implicite ACTUEL en overrides explicites AVANT de fermer les projets : sans
    # ça, `default_access='no_access'` couperait immédiatement tout compte qui n'a jamais eu
    # besoin d'une exception — soit tout le monde, puisque c'est précisément le trou que ce
    # correctif comble pour l'avenir, pas une régression à faire subir aux équipes déjà en place.
    op.execute(
        'INSERT INTO project_access (project_id, user_id, role) '
        'SELECT p.id, u.id, u.role FROM project p CROSS JOIN "user" u '
        "WHERE p.default_access='' AND NOT EXISTS ("
        '  SELECT 1 FROM project_access pa WHERE pa.project_id=p.id AND pa.user_id=u.id)')
    op.execute("UPDATE project SET default_access='no_access' WHERE default_access=''")
    # La projection ne doit pas continuer d'afficher les anciennes attributions implicites.
    op.execute("UPDATE project_member SET status='removed' WHERE NOT EXISTS "
               "(SELECT 1 FROM project_access pa WHERE pa.project_id=project_member.project_id "
               "AND pa.user_id=project_member.user_id AND pa.role<>'no_access') "
               "AND project_id IN (SELECT id FROM project WHERE default_access='no_access')")


def downgrade():
    op.drop_column("user", "password_expires_at")
    op.drop_column("user", "must_change_password")
