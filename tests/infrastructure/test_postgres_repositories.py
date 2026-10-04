"""Integration tests for PostgreSQL repository implementations.

Requires Docker (testcontainers spins up pgvector/pgvector:pg16).
Run with: pytest --integration
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
)
from findocbot.domain.exceptions import (
    DuplicateDocumentError,
    EmbeddingDimensionError,
    StorageError,
)
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChatHistoryRepository,
    PostgresChunkRepository,
    PostgresDocumentRepository,
)

EMBEDDING_DIM = 768
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _migration_sql(embedding_dim: int) -> str:
    """Real migrations with the psql variable apply.sh would set."""
    return "\n".join(
        path.read_text().replace(":embedding_dim", str(embedding_dim))
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql"))
    )


def _run_migration_sync(dsn: str) -> None:
    """Apply schema migration to the test database (blocking)."""

    async def _migrate() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(_migration_sql(EMBEDDING_DIM))
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
        # driver=None yields a plain postgresql:// DSN; the default appends
        # +psycopg2, which asyncpg rejects.
        dsn = postgres.get_connection_url(driver=None)
        _run_migration_sync(dsn)
        yield dsn


@pytest.fixture
async def db_pool(pg_dsn: str) -> PostgresPool:
    """Create a pool connected to the test PostgreSQL."""
    pool = PostgresPool(pg_dsn)
    await pool.start()
    # The container is module-scoped; wipe data so tests stay independent.
    await pool.pool.execute("TRUNCATE chunks, documents, chat_turns, sessions")
    yield pool
    await pool.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_create_new_document_persists_row(
    db_pool: PostgresPool,
) -> None:
    """Document row can be persisted via the repository."""
    repo = PostgresDocumentRepository(db_pool)
    doc = Document.create(filename="test.pdf")
    await repo.create(doc)

    row = await db_pool.pool.fetchrow(
        "SELECT id, filename FROM documents WHERE id = $1", doc.id
    )
    assert row is not None
    assert row["filename"] == "test.pdf"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chunk_search_after_insert_returns_closest_first(
    db_pool: PostgresPool,
) -> None:
    """Chunks with embeddings can be persisted and searched by vector."""
    repo = PostgresChunkRepository(db_pool, EMBEDDING_DIM)
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
    embeddings = [[0.0] * EMBEDDING_DIM, [0.0] * EMBEDDING_DIM]
    # Zero vectors have no cosine direction and HNSW skips them, so both
    # vectors are non-zero; the second points the same way as the query.
    embeddings[0][1] = 0.9
    embeddings[1][0] = 0.9

    await repo.add_chunks_with_embeddings(chunks, embeddings)

    query_embedding = [0.5] + [0.0] * (EMBEDDING_DIM - 1)
    results = await repo.search_by_embedding(query_embedding, top_k=2)

    assert len(results) == 2
    assert results[0].chunk.chunk_index == 1
    # asyncpg returns UUID objects — verify they are converted to str.
    assert isinstance(results[0].chunk.id, str)
    assert isinstance(results[0].chunk.document_id, str)


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
@pytest.mark.asyncio
async def test_chunk_search_empty_table_returns_empty_list(
    db_pool: PostgresPool,
) -> None:
    """Search with no indexed chunks returns empty list."""
    repo = PostgresChunkRepository(db_pool, EMBEDDING_DIM)
    results = await repo.search_by_embedding([1.0] * EMBEDDING_DIM, top_k=5)
    assert results == []


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
    repo = PostgresChunkRepository(db_pool, 1024)

    with pytest.raises(EmbeddingDimensionError, match="vector\\(768\\)"):
        await repo.verify_schema()


@pytest.mark.integration
async def test_chunk_insert_wrong_dim_raises_before_writing(
    db_pool: PostgresPool,
) -> None:
    doc = Document.create(filename="dim.pdf")
    await PostgresDocumentRepository(db_pool).create(doc)
    repo = PostgresChunkRepository(db_pool, EMBEDDING_DIM)
    chunk = Chunk.create(document_id=doc.id, chunk_index=0, text="x")

    with pytest.raises(EmbeddingDimensionError, match="has 3 dimensions"):
        await repo.add_chunks_with_embeddings([chunk], [[0.1, 0.2, 0.3]])

    assert await db_pool.pool.fetchval("SELECT count(*) FROM chunks") == 0


@pytest.mark.integration
async def test_document_find_by_content_hash_after_create_returns_it(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    doc = Document.create(filename="a.pdf", content_hash="abc")
    await repo.create(doc)

    assert await repo.find_by_content_hash("abc") == doc


@pytest.mark.integration
async def test_document_create_same_content_hash_raises_duplicate(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    await repo.create(Document.create(filename="a.pdf", content_hash="abc"))

    duplicate = Document.create(filename="b.pdf", content_hash="abc")

    with pytest.raises(DuplicateDocumentError):
        await repo.create(duplicate)


@pytest.mark.integration
async def test_document_create_two_without_hash_keeps_both(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    await repo.create(Document.create(filename="a.pdf"))
    await repo.create(Document.create(filename="b.pdf"))

    assert await db_pool.pool.fetchval("SELECT count(*) FROM documents") == 2


@pytest.mark.integration
async def test_document_list_page_returns_newest_first(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    older = Document.create(filename="older.pdf")
    newer = Document.create(filename="newer.pdf")
    await repo.create(older)
    await repo.create(newer)

    page = await repo.list_page(limit=1, offset=0)

    assert [doc.id for doc in page] == [newer.id]


@pytest.mark.integration
async def test_document_get_after_create_returns_it(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    doc = Document.create(filename="a.pdf", content_hash="abc")
    await repo.create(doc)

    assert await repo.get(doc.id) == doc


@pytest.mark.integration
async def test_document_delete_removes_its_chunks_from_search(
    db_pool: PostgresPool,
) -> None:
    doc = Document.create(filename="a.pdf")
    documents = PostgresDocumentRepository(db_pool)
    await documents.create(doc)
    chunks = PostgresChunkRepository(db_pool, EMBEDDING_DIM)
    embedding = [0.5] + [0.0] * (EMBEDDING_DIM - 1)
    await chunks.add_chunks_with_embeddings(
        [Chunk.create(document_id=doc.id, chunk_index=0, text="x")],
        [embedding],
    )

    await documents.delete(doc.id)

    assert await chunks.search_by_embedding(embedding, top_k=5) == []


@pytest.mark.integration
async def test_document_delete_twice_reports_whether_it_existed(
    db_pool: PostgresPool,
) -> None:
    repo = PostgresDocumentRepository(db_pool)
    doc = Document.create(filename="a.pdf")
    await repo.create(doc)

    assert (await repo.delete(doc.id), await repo.delete(doc.id)) == (
        True,
        False,
    )


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


@pytest.fixture
def unstarted_repo() -> PostgresChunkRepository:
    # The pool is never started: the check must fire before any DB access.
    return PostgresChunkRepository(PostgresPool("postgresql://unused"), 3)


async def test_chunk_insert_wrong_dim_raises_without_db_access(
    unstarted_repo: PostgresChunkRepository,
) -> None:
    chunk = Chunk.create(document_id="d", chunk_index=0, text="x")

    with pytest.raises(EmbeddingDimensionError, match="has 2 dimensions"):
        await unstarted_repo.add_chunks_with_embeddings([chunk], [[0.1, 0.2]])


async def test_chunk_search_wrong_dim_raises_without_db_access(
    unstarted_repo: PostgresChunkRepository,
) -> None:
    with pytest.raises(EmbeddingDimensionError, match="EMBEDDING_DIM is 3"):
        await unstarted_repo.search_by_embedding([0.1] * 4, top_k=1)
