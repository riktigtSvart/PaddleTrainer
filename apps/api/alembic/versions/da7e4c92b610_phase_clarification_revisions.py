"""Add source-bound answer revisions; do not change any existing table.

Revision ID: da7e4c92b610
Revises: c91f7a3e2d40
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'da7e4c92b610'
down_revision = 'c91f7a3e2d40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('phase_clarification_revisions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('previous_revision_id', sa.Uuid(), nullable=True),
        sa.Column('artifact_id', sa.String(100), nullable=False),
        sa.Column('rules_version', sa.String(100), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('plan_sha256', sa.String(64), nullable=False),
        sa.Column('motion_input_sha256', sa.String(64), nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('request_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('evidence_gzip', sa.LargeBinary(), nullable=False),
        sa.Column('record_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['workout_sessions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('session_id', 'sequence', name='uq_phase_clarification_sequence'),
        sa.UniqueConstraint('session_id', 'request_sha256', name='uq_phase_clarification_request'),
        sa.CheckConstraint('sequence > 0', name='ck_phase_clarification_sequence'),
    )
    op.create_index('ix_phase_clarification_owner_session', 'phase_clarification_revisions', ['user_id', 'session_id', 'sequence'])


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError('PHASE_STORAGE_DOWNGRADE_REQUIRES_ONLINE_EMPTY_TABLE_CHECK')
    count = op.get_bind().execute(sa.text('SELECT count(*) FROM phase_clarification_revisions')).scalar_one()
    if count:
        raise RuntimeError('PHASE_STORAGE_DOWNGRADE_REFUSES_SAVED_ANSWERS')
    op.drop_index('ix_phase_clarification_owner_session', table_name='phase_clarification_revisions')
    op.drop_table('phase_clarification_revisions')
