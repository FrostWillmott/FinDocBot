"""Shared fixtures for the integration tests: a real PostgreSQL.

Requires Docker (testcontainers spins up pgvector/pgvector:pg16).
"""

from __future__ import annotations

import pytest
from testcontainers.postgres import PostgresContainer

from findocbot.infrastructure.db import PostgresPool
from tests.migrations import run_migrations

# Mirrors Settings.embedding_dim, which leads (the e2e tests read it there).
EMBEDDING_DIM = 1024


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    """Spin up pgvector container once per test module."""
    with PostgresContainer(
        # docker-compose.yml leads for the image tag; bump it there first.
        image="pgvector/pgvector:pg16",
        dbname="findocbot",
    ) as postgres:
        # driver=None yields a plain postgresql:// DSN; the default appends
        # +psycopg2, which asyncpg rejects.
        dsn = postgres.get_connection_url(driver=None)
        run_migrations(dsn, EMBEDDING_DIM)
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
