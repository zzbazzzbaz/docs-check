"""extend users

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('name', sa.String(length=64), nullable=False, server_default=''),
    )
    op.add_column(
        'users',
        sa.Column('major', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('teacher_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_foreign_key(None, 'users', 'users', ['teacher_id'], ['id'])
    op.create_index('ix_users_teacher_id', 'users', ['teacher_id'])
    op.execute("UPDATE users SET role = 'student' WHERE role = 'user'")
    op.alter_column('users', 'role', server_default='student')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'role', server_default='user')
    op.drop_index('ix_users_teacher_id', table_name='users')
    op.drop_constraint('users_teacher_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'teacher_id')
    op.drop_column('users', 'major')
    op.drop_column('users', 'name')
