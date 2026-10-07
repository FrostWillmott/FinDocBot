"""Initial schema: documents, chunks, chat_turns and the vector extension.

Revision ID: 0001
Revises:
Create Date: 2026-02-05
"""

from __future__ import annotations

import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Sizes chunks.embedding; must match the embedding model's output size.
_EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "768"))


def upgrade() -> None:
    """Create the pgvector extension and the core tables."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            filename TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL
                REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            section TEXT NULL,
            content TEXT NOT NULL,
            embedding VECTOR({_EMBEDDING_DIM}) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_chunks_document_id ON chunks(document_id)")
    op.execute(
        """
        CREATE TABLE chat_turns (
            id UUID PRIMARY KEY,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_chat_turns_session_created "
        "ON chat_turns(session_id, created_at DESC)"
    )


def downgrade() -> None:
    """Drop the core tables in reverse dependency order."""
    op.execute("DROP TABLE chat_turns")
    op.execute("DROP TABLE chunks")
    op.execute("DROP TABLE documents")
