"""Document ingestion status and error message.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add documents.status and documents.error columns."""
    # Rows indexed before background ingestion default to 'ready': they were
    # parsed and embedded synchronously at upload time.
    op.execute(
        "ALTER TABLE documents ADD COLUMN status TEXT NOT NULL "
        "DEFAULT 'ready' "
        "CHECK (status IN ('pending', 'ready', 'failed'))"
    )
    op.execute("ALTER TABLE documents ADD COLUMN error TEXT NULL")


def downgrade() -> None:
    """Drop the status and error columns."""
    op.execute("ALTER TABLE documents DROP COLUMN error")
    op.execute("ALTER TABLE documents DROP COLUMN status")
