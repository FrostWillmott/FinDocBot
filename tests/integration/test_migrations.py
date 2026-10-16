"""Alembic revisions that change stored data, run against a real PostgreSQL."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import asyncpg
import pytest

from tests.migrations import revert_migrations, run_migrations

_OLD_DIM = 768
_NEW_DIM = 1024


def _vector(dim: int) -> str:
    return "[" + ",".join(["0.1"] * dim) + "]"


async def _column_dim(dsn: str) -> int:
    connection = await asyncpg.connect(dsn)
    try:
        return int(
            await connection.fetchval(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            )
        )
    finally:
        await connection.close()


@pytest.fixture
async def indexed_768_database(pg_dsn: str) -> AsyncGenerator[str, None]:
    """A database as 0005 left it, with one ready document and one chunk."""
    connection = await asyncpg.connect(pg_dsn)
    try:
        await connection.execute(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public"
        )
        run_migrations(pg_dsn, _OLD_DIM, revision="0005")
        await connection.execute(
            "INSERT INTO documents (id, filename) "
            "VALUES ('00000000-0000-0000-0000-000000000001', 'report.pdf')"
        )
        await connection.execute(
            "INSERT INTO chunks "
            "(id, document_id, chunk_index, content, embedding) "
            "VALUES ('00000000-0000-0000-0000-000000000002', "
            "'00000000-0000-0000-0000-000000000001', 0, 'Revenue', "
            "$1::vector)",
            _vector(_OLD_DIM),
        )
    finally:
        await connection.close()
    yield pg_dsn


@pytest.mark.integration
async def test_upgrade_768_database_to_1024_resizes_the_embedding_column(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _NEW_DIM)

    assert await _column_dim(indexed_768_database) == _NEW_DIM


@pytest.mark.integration
async def test_upgrade_768_database_to_1024_leaves_no_chunks(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _NEW_DIM)

    connection = await asyncpg.connect(indexed_768_database)
    try:
        assert await connection.fetchval("SELECT count(*) FROM chunks") == 0
    finally:
        await connection.close()


@pytest.mark.integration
async def test_upgrade_768_database_to_1024_marks_the_document_failed(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _NEW_DIM)

    connection = await asyncpg.connect(indexed_768_database)
    try:
        row = await connection.fetchrow(
            "SELECT status, error FROM documents WHERE filename = 'report.pdf'"
        )
    finally:
        await connection.close()
    assert tuple(row) == (
        "failed",
        "The embedding model changed; upload the document again.",
    )


@pytest.mark.integration
async def test_upgrade_768_database_to_1024_keeps_the_hnsw_cosine_index(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _NEW_DIM)

    connection = await asyncpg.connect(indexed_768_database)
    try:
        definition = await connection.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'idx_chunks_embedding_hnsw'"
        )
    finally:
        await connection.close()
    assert definition == (
        "CREATE INDEX idx_chunks_embedding_hnsw ON public.chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m='16', ef_construction='64')"
    )


@pytest.mark.integration
async def test_upgrade_with_matching_dimension_keeps_the_chunks(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _OLD_DIM)

    connection = await asyncpg.connect(indexed_768_database)
    try:
        assert await connection.fetchval("SELECT count(*) FROM chunks") == 1
    finally:
        await connection.close()


@pytest.mark.integration
async def test_upgrade_with_matching_dimension_keeps_the_document_ready(
    indexed_768_database: str,
) -> None:
    run_migrations(indexed_768_database, _OLD_DIM)

    connection = await asyncpg.connect(indexed_768_database)
    try:
        status = await connection.fetchval(
            "SELECT status FROM documents WHERE filename = 'report.pdf'"
        )
    finally:
        await connection.close()
    assert status == "ready"


@pytest.mark.integration
async def test_upgrade_without_embedding_dim_sizes_the_column_to_1024(
    pg_dsn: str,
) -> None:
    connection = await asyncpg.connect(pg_dsn)
    try:
        await connection.execute(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public"
        )
    finally:
        await connection.close()

    run_migrations(pg_dsn, None)

    assert await _column_dim(pg_dsn) == _NEW_DIM


@pytest.mark.integration
async def test_downgrade_from_1024_restores_the_768_column(
    pg_dsn: str,
) -> None:
    connection = await asyncpg.connect(pg_dsn)
    try:
        await connection.execute(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public"
        )
    finally:
        await connection.close()
    run_migrations(pg_dsn, _NEW_DIM)

    revert_migrations(pg_dsn, "0005")

    assert await _column_dim(pg_dsn) == _OLD_DIM
