"""create users

Revision ID: 0001
Revises:
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=32), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False, server_default='student'),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('major', sa.String(length=64), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_teacher_id', 'users', ['teacher_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_users_teacher_id', table_name='users')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')
