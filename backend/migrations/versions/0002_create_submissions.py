"""create submissions

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_dir', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('task_error', sa.String(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fail_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('undetermined_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('not_run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unrecognised_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('by_scope', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ruleset_version', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_submissions_student_id', 'submissions', ['student_id'])
    op.create_index('ix_submissions_status', 'submissions', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_submissions_status', table_name='submissions')
    op.drop_index('ix_submissions_student_id', table_name='submissions')
    op.drop_table('submissions')
