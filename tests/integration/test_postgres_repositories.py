"""Integration tests for what only the PostgreSQL repositories do.

The behaviour shared with the in-memory fakes is in
``test_postgres_repository_contract.py``. Requires Docker (testcontainers
spins up pgvector/pgvector:pg16). Run with: pytest --integration
"""

from __future__ import annotations

import pytest

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
)
from findocbot.domain.exceptions import (
    EmbeddingDimensionError,
    StorageError,
)
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChatHistoryRepository,
    PostgresChunkRepository,
    PostgresDocumentRepository,
)
from tests.integration.conftest import EMBEDDING_DIM


@pytest.mark.integration
@pytest.mark.asyncio
async def test_history_list_recent_after_adds_returns_oldest_first(
    db_pool: PostgresPool,
) -> None:
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


@pytest.mark.integration
async def test_verify_schema_matching_dim_returns_none(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresChunkRepository(db_pool, EMBEDDING_DIM)

    assert await repo.verify_schema() is None


@pytest.mark.integration
async def test_verify_schema_mismatched_dim_raises_dimension_error(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresChunkRepository(db_pool, 768)

    with pytest.raises(EmbeddingDimensionError, match="vector\\(1024\\)"):
        await repo.verify_schema()


@pytest.mark.integration
async def test_chunk_insert_wrong_dim_raises_before_writing(
    db_pool: PostgresPool,
) -> None:
    doc = Document.create(filename="dim.pdf", status="ready")
    await PostgresDocumentRepository(db_pool).create(doc)
    repo = PostgresChunkRepository(db_pool, EMBEDDING_DIM)
    chunk = Chunk.create(document_id=doc.id, chunk_index=0, text="x")

    with pytest.raises(EmbeddingDimensionError, match="has 3 dimensions"):
        await repo.replace_document_chunks(doc.id, [chunk], [[0.1, 0.2, 0.3]])

    assert await db_pool.pool.fetchval("SELECT count(*) FROM chunks") == 0


@pytest.mark.integration
async def test_session_exists_after_create_returns_true(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresChatHistoryRepository(db_pool)
    session = ChatSession.create()
    await repo.create_session(session)

    assert await repo.session_exists(session.id) is True


@pytest.mark.integration
async def test_session_exists_never_issued_id_returns_false(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresChatHistoryRepository(db_pool)

    assert await repo.session_exists("guessed-id") is False


@pytest.mark.integration
async def test_ping_running_database_returns_none(
    db_pool: PostgresPool,
) -> None:
    assert await db_pool.ping() is None


@pytest.mark.integration
async def test_ping_closed_pool_raises_storage_error(pg_dsn: str) -> None:
    db = PostgresPool(pg_dsn)
    await db.start()
    await db.pool.close()

    with pytest.raises(StorageError, match="Database is unavailable"):
        await db.ping()
