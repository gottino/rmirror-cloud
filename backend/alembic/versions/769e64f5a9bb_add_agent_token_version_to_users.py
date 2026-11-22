"""add agent_token_version to users

Revision ID: 769e64f5a9bb
Revises: 95cf6385d77b
Create Date: 2026-11-11

Agent tokens are stateless JWTs. To make them revocable, each user gets a
token version: new agent tokens carry it as their ``ver`` claim, and the
backend rejects an agent token whose ``ver`` differs from the user's current
version. ``POST /auth/agent-token/revoke`` increments it, which invalidates
every agent token of that user.

Existing rows start at 0. Tokens issued before this change have no ``ver``
claim and are treated as version 0, so they keep working until the user
revokes.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "769e64f5a9bb"
down_revision: Union[str, Sequence[str], None] = "95cf6385d77b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "agent_token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "agent_token_version")
