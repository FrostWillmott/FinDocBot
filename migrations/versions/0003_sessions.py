"""Server-issued chat sessions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the sessions table that gates /ask session ids."""
    # /ask accepts only ids listed here, so a client cannot pick, guess or
    # reuse another client's session id. No FK from chat_turns: turns stored
    # before this migration carry client-chosen ids with no row here; they
    # simply become unreachable.
    op.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    """Drop the sessions table."""
    op.execute("DROP TABLE sessions")
