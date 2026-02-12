"""add_beta_invite_columns_to_waitlist

Revision ID: c4d5e6f7a8b9
Revises: b3c7e1f2a4d6
Create Date: 2026-02-11 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c7e1f2a4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    """Create waitlist table if needed, then add beta invite columns."""
    if not _table_exists('waitlist'):
        # Table was never created via migration (only via Base.metadata.create_all)
        # Create it fresh with all columns including unique constraints inline
        op.create_table(
            'waitlist',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('email', sa.String(), nullable=False, unique=True),
            sa.Column('name', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('invite_token', sa.String(length=512), nullable=True, unique=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('claimed_at', sa.DateTime(), nullable=True),
            sa.Column('claimed_by', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_waitlist_id', 'waitlist', ['id'])
        op.create_index('ix_waitlist_email', 'waitlist', ['email'], unique=True)
    else:
        # Table exists (production PostgreSQL) — add new columns
        op.add_column('waitlist', sa.Column('name', sa.String(length=255), nullable=True))
        op.add_column('waitlist', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
        op.add_column('waitlist', sa.Column('invite_token', sa.String(length=512), nullable=True))
        op.add_column('waitlist', sa.Column('approved_at', sa.DateTime(), nullable=True))
        op.add_column('waitlist', sa.Column('claimed_at', sa.DateTime(), nullable=True))
        op.add_column('waitlist', sa.Column('claimed_by', sa.String(length=255), nullable=True))
        op.create_unique_constraint('uq_waitlist_invite_token', 'waitlist', ['invite_token'])


def downgrade() -> None:
    """Remove beta invite columns from waitlist table."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == 'sqlite':
        # SQLite: use batch mode for constraint changes
        with op.batch_alter_table('waitlist') as batch_op:
            batch_op.drop_column('claimed_by')
            batch_op.drop_column('claimed_at')
            batch_op.drop_column('approved_at')
            batch_op.drop_column('invite_token')
            batch_op.drop_column('status')
            batch_op.drop_column('name')
    else:
        op.drop_constraint('uq_waitlist_invite_token', 'waitlist', type_='unique')
        op.drop_column('waitlist', 'claimed_by')
        op.drop_column('waitlist', 'claimed_at')
        op.drop_column('waitlist', 'approved_at')
        op.drop_column('waitlist', 'invite_token')
        op.drop_column('waitlist', 'status')
        op.drop_column('waitlist', 'name')
