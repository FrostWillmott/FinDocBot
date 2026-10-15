"""Integration tests for the production wiring in create_container.

Requires Docker (see conftest.py). Ollama is not needed: starting its gateway
only builds an HTTP client.
"""

from __future__ import annotations

import pytest

from findocbot.config import Settings
from findocbot.infrastructure.container import create_container
from findocbot.infrastructure.db import PostgresPool


@pytest.mark.integration
async def test_startup_marks_documents_left_pending_by_a_restart_failed(
    pg_dsn: str, db_pool: PostgresPool
) -> None:
    await db_pool.pool.execute(
        """
        INSERT INTO documents (id, filename, content_hash, status)
        VALUES (gen_random_uuid(), 'left.pdf', 'h1', 'pending'),
               (gen_random_uuid(), 'done.pdf', 'h2', 'ready')
        """
    )
    container = create_container(
        Settings(_env_file=None, postgres_dsn=pg_dsn, embedding_dim=768)
    )

    await container.startup()
    try:
        rows = await db_pool.pool.fetch(
            "SELECT filename, status FROM documents ORDER BY filename"
        )
    finally:
        await container.shutdown()

    assert [(row["filename"], row["status"]) for row in rows] == [
        ("done.pdf", "ready"),
        ("left.pdf", "failed"),
    ]
