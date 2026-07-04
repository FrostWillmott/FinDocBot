"""Integration tests for PostgreSQL repository implementations.

Requires Docker (testcontainers spins up pgvector/pgvector:pg16).
Run with: pytest --integration
"""

import asyncio

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from findocbot.domain.entities import ChatTurn, Chunk, Document
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChatHistoryRepository,
    PostgresChunkRepository,
    PostgresDocumentRepository,
)

pytestmark = pytest.mark.integration

_MIGRATION_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section TEXT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_turns (
    id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _run_migration_sync(dsn: str) -> None:
    """Apply schema migration to the test database (blocking)."""

    async def _migrate() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(_MIGRATION_SQL)
        finally:
            await conn.close()

    asyncio.run(_migrate())


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    """Spin up pgvector container once per test module."""
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        dbname="findocbot",
    ) as postgres:
        dsn = postgres.get_connection_url()
        _run_migration_sync(dsn)
        yield dsn


@pytest.fixture
async def db_pool(pg_dsn: str) -> PostgresPool:
    """Create a pool connected to the test PostgreSQL."""
    pool = PostgresPool(pg_dsn)
    await pool.start()
    yield pool
    await pool.stop()


@pytest.mark.asyncio
async def test_document_create_and_retrieve(pg_dsn: str) -> None:
    """Document row can be persisted via the repository."""
    pool = PostgresPool(pg_dsn)
    await pool.start()
    try:
        repo = PostgresDocumentRepository(pool)
        doc = Document.create(filename="test.pdf")
        await repo.create(doc)

        row = await pool.pool.fetchrow(
            "SELECT id, filename FROM documents WHERE id = $1", doc.id
        )
        assert row is not None
        assert row["filename"] == "test.pdf"
    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_chunk_insert_and_search(db_pool: PostgresPool) -> None:
    """Chunks with embeddings can be persisted and searched by vector."""
    repo = PostgresChunkRepository(db_pool)
    doc = Document.create(filename="report.pdf")
    doc_repo = PostgresDocumentRepository(db_pool)
    await doc_repo.create(doc)

    chunks = [
        Chunk.create(document_id=doc.id, chunk_index=i, text=text)
        for i, text in enumerate([
            "Revenue grew by 20%",
            "Profit remained stable",
        ])
    ]
    embeddings = [[0.0] * 768, [0.0] * 768]
    embeddings[1][0] = 0.9  # Make the second vector closer to query

    await repo.add_chunks_with_embeddings(chunks, embeddings)

    query_embedding = [0.5] + [0.0] * 767
    results = await repo.search_by_embedding(query_embedding, top_k=2)

    assert len(results) == 2
    assert results[0].chunk.chunk_index == 1
    # asyncpg returns UUID objects — verify they are converted to str.
    assert isinstance(results[0].chunk.id, str)
    assert isinstance(results[0].chunk.document_id, str)


@pytest.mark.asyncio
async def test_chat_history_add_and_list(db_pool: PostgresPool) -> None:
    """Chat turns are persisted and listed in chronological order."""
    repo = PostgresChatHistoryRepository(db_pool)

    turn1 = ChatTurn.create(session_id="session-1", question="Q1", answer="A1")
    turn2 = ChatTurn.create(session_id="session-1", question="Q2", answer="A2")

    await repo.add_turn(turn1)
    await repo.add_turn(turn2)

    recent = await repo.list_recent(session_id="session-1", limit=10)
    assert len(recent) == 2
    assert recent[0].question == "Q1"
    assert recent[1].question == "Q2"
    assert isinstance(recent[0].id, str)


@pytest.mark.asyncio
async def test_search_empty_when_no_chunks(
    db_pool: PostgresPool,
) -> None:
    """Search with no indexed chunks returns empty list."""
    repo = PostgresChunkRepository(db_pool)
    results = await repo.search_by_embedding([1.0] * 768, top_k=5)
    assert results == []
