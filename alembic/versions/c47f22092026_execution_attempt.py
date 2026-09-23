"""Tentatives physiques, résultats et artefacts indépendants des rejeux."""
import sqlalchemy as sa
from alembic import op

revision = 'c47f22092026'
down_revision = 'b46f18092026'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('observation_evidence', 'generation_provenance', 'technical_plan'):
        op.add_column('test_case_version', sa.Column(name, sa.Text(), nullable=False, server_default=''))
    op.create_table(
        'execution_attempt',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('execution_id', sa.Integer(), sa.ForeignKey('execution.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('started_at', sa.Text(), nullable=False),
        sa.Column('finished_at', sa.Text(), nullable=False, server_default=''),
        sa.Column('execution_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('functional_status', sa.Text(), nullable=False, server_default='indetermine'),
        sa.Column('duration_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('artifacts_path', sa.Text(), nullable=False, server_default=''),
        sa.Column('provenance', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('result_json', sa.Text(), nullable=False, server_default='{}'),
        sa.CheckConstraint('attempt_number > 0', name='ck_execution_attempt_number'),
        sa.UniqueConstraint('execution_id', 'attempt_number', name='uq_execution_attempt_number'),
        sqlite_autoincrement=True,
    )


def downgrade():
    op.drop_table('execution_attempt')
    for name in ('observation_evidence', 'generation_provenance', 'technical_plan'):
        op.drop_column('test_case_version', name)
