"""Content hash for upload deduplication.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add documents.content_hash and its unique index."""
    # SHA-256 of the uploaded bytes; the unique index makes a re-upload of the
    # same PDF resolve to the existing document instead of a second copy.
    # Rows from before this migration keep NULL (their bytes were not stored),
    # and NULLs never collide, so existing duplicates stay until deleted.
    op.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
    op.execute(
        "CREATE UNIQUE INDEX idx_documents_content_hash "
        "ON documents(content_hash)"
    )


def downgrade() -> None:
    """Drop the unique index and the content_hash column."""
    op.execute("DROP INDEX idx_documents_content_hash")
    op.execute("ALTER TABLE documents DROP COLUMN content_hash")
