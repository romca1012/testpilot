"""Jeton d'accès à usage unique d'une session live (enregistrement assisté du chemin de connexion)."""
import sqlalchemy as sa
from alembic import op

revision = 'd8a3f5c1e947'
down_revision = 'b3f7d4a291ec'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'live_session_token',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('project.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False, unique=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Text(), nullable=False),
        sa.Column('used_at', sa.Text(), nullable=False, server_default=''),
        sqlite_autoincrement=True,
    )


def downgrade():
    op.drop_table('live_session_token')
