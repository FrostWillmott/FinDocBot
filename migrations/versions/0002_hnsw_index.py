"""HNSW index over chunks.embedding for approximate nearest-neighbour search.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the HNSW cosine index used by /search and /ask."""
    # HNSW offers lower query latency and better recall than ivfflat without
    # requiring training data; ivfflat has been removed in favour of HNSW.
    op.execute(
        "CREATE INDEX idx_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Drop the HNSW index."""
    op.execute("DROP INDEX idx_chunks_embedding_hnsw")
