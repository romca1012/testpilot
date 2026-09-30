"""Descripteur du formulaire de connexion capturé par 3 clics guidés (extension du lot
« Enregistrement assisté du chemin de connexion » — 2026-09-30)."""
import sqlalchemy as sa
from alembic import op

revision = 'a2d47f9c8e15'
down_revision = 'e1c6a9f2b830'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'project_login_recording',
        sa.Column('login_form_json', sa.Text(), nullable=False, server_default=''))


def downgrade():
    op.drop_column('project_login_recording', 'login_form_json')
