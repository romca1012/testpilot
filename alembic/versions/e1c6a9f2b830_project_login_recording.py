"""Séquence de connexion confirmée d'une session live (enregistrement assisté du chemin de connexion)."""
import sqlalchemy as sa
from alembic import op

revision = 'e1c6a9f2b830'
down_revision = 'd8a3f5c1e947'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'project_login_recording',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('project.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('steps_json', sa.Text(), nullable=False),
        sa.Column('recorded_at', sa.Text(), nullable=False),
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'),
                  nullable=False),
        sqlite_autoincrement=True,
    )


def downgrade():
    op.drop_table('project_login_recording')
