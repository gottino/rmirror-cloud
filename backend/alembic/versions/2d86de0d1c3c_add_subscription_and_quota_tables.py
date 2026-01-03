"""add_subscription_and_quota_tables

Revision ID: 2d86de0d1c3c
Revises: 5ae75127c19e
Create Date: 2026-01-03 17:18:37.758535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d86de0d1c3c'
down_revision: Union[str, Sequence[str], None] = '5ae75127c19e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subscriptions and quota_usage tables for quota system and billing."""

    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False, server_default='free'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('current_period_start', sa.DateTime(), nullable=True),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_subscriptions_user_id')
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'], unique=True)
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'], unique=True)

    # Create quota_usage table
    op.create_table(
        'quota_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('quota_type', sa.String(20), nullable=False, server_default='ocr'),
        sa.Column('limit', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reset_at', sa.DateTime(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_quota_usage_user_id', 'quota_usage', ['user_id'])
    op.create_index('idx_quota_user_type', 'quota_usage', ['user_id', 'quota_type'], unique=True)

    # Initialize subscriptions for existing users
    connection = op.get_bind()

    # Check if we're using SQLite or PostgreSQL
    if connection.dialect.name == 'sqlite':
        # SQLite syntax
        connection.execute(sa.text("""
            INSERT INTO subscriptions (user_id, tier, status, current_period_start, current_period_end)
            SELECT id, 'free', 'active', datetime('now'), datetime('now', '+30 days')
            FROM users
        """))

        connection.execute(sa.text("""
            INSERT INTO quota_usage (user_id, quota_type, "limit", used, reset_at, period_start)
            SELECT id, 'ocr', 30, 0, datetime('now', '+30 days'), datetime('now')
            FROM users
        """))
    else:
        # PostgreSQL syntax
        connection.execute(sa.text("""
            INSERT INTO subscriptions (user_id, tier, status, current_period_start, current_period_end)
            SELECT id, 'free', 'active', NOW(), NOW() + INTERVAL '30 days'
            FROM users
        """))

        connection.execute(sa.text("""
            INSERT INTO quota_usage (user_id, quota_type, "limit", used, reset_at, period_start)
            SELECT id, 'ocr', 30, 0, NOW() + INTERVAL '30 days', NOW()
            FROM users
        """))

    print("✓ Created subscriptions and quota_usage tables")
    print(f"✓ Initialized {connection.execute(sa.text('SELECT COUNT(*) FROM subscriptions')).scalar()} user subscriptions")


def downgrade() -> None:
    """Remove subscriptions and quota_usage tables."""
    op.drop_index('idx_quota_user_type', table_name='quota_usage')
    op.drop_index('ix_quota_usage_user_id', table_name='quota_usage')
    op.drop_table('quota_usage')

    op.drop_index('ix_subscriptions_stripe_subscription_id', table_name='subscriptions')
    op.drop_index('ix_subscriptions_stripe_customer_id', table_name='subscriptions')
    op.drop_index('ix_subscriptions_user_id', table_name='subscriptions')
    op.drop_table('subscriptions')
