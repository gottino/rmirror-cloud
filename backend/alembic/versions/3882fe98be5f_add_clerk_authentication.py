"""add_clerk_authentication

Revision ID: 3882fe98be5f
Revises: 2d96f4a915f4
Create Date: 2025-11-23 21:01:19.685427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3882fe98be5f'
down_revision: Union[str, Sequence[str], None] = '2d96f4a915f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add clerk_user_id column
    op.add_column('users', sa.Column('clerk_user_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_clerk_user_id'), 'users', ['clerk_user_id'], unique=True)

    # Make hashed_password nullable (for Clerk users)
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('hashed_password',
                   existing_type=sa.String(length=255),
                   nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Make hashed_password non-nullable again
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('hashed_password',
                   existing_type=sa.String(length=255),
                   nullable=False)

    # Remove clerk_user_id column
    op.drop_index(op.f('ix_users_clerk_user_id'), table_name='users')
    op.drop_column('users', 'clerk_user_id')
