"""Resize chunks.embedding to the embedding model's output size.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

from findocbot.config import Settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Same variable, and the same default, as the app reads, so the column and
# the setting cannot start out disagreeing.
_EMBEDDING_DIM = int(
    os.environ.get(
        "EMBEDDING_DIM", Settings.model_fields["embedding_dim"].default
    )
)
# What 0001 creates when EMBEDDING_DIM is unset (nomic-embed-text).
_PREVIOUS_DIM = 768


def _resize_embedding_column(dim: int) -> None:
    """Retype chunks.embedding, discarding vectors of the old size."""
    current = (
        op
        .get_bind()
        .execute(
            sa.text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            )
        )
        .scalar_one()
    )
    if current == dim:
        return
    # pgvector cannot cast between sizes, and vectors from a different model
    # are meaningless to the new one, so the chunks go; their text is not kept.
    op.execute("DELETE FROM chunks")
    # A failed document is retried when it is uploaded again (the duplicate
    # check releases it), so the re-embed needs no new mechanism. Rows from
    # before 0004 have no content_hash and are not found: the upload makes
    # a new document and the old row has to be deleted.
    op.execute(
        "UPDATE documents SET status = 'failed', "
        "error = 'The embedding model changed; upload the document again.' "
        "WHERE status <> 'failed'"
    )
    # Postgres rebuilds the HNSW index (same parameters) with the new type.
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE VECTOR({dim})")


def upgrade() -> None:
    """Size chunks.embedding to EMBEDDING_DIM."""
    _resize_embedding_column(_EMBEDDING_DIM)


def downgrade() -> None:
    """Restore the size 0001 uses without EMBEDDING_DIM."""
    _resize_embedding_column(_PREVIOUS_DIM)
