"""Integration tests for the production wiring in create_container.

Requires Docker (see conftest.py). Ollama is not needed: starting its gateway
only builds an HTTP client.
"""

from __future__ import annotations

import math

import httpx
import pytest
import respx

from findocbot.config import Settings
from findocbot.domain.entities import Chunk, Document
from findocbot.infrastructure.container import create_container
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChunkRepository,
    PostgresDocumentRepository,
)
from tests.fakes import rerank_reply


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
        Settings(_env_file=None, postgres_dsn=pg_dsn, embedding_dim=_DIM)
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


_OLLAMA = "http://ollama.test:11434"
_DIM = 1024
_QUERY = [1.0] + [0.0] * (_DIM - 1)


async def _seed_three_chunks(db_pool: PostgresPool) -> None:
    """Chunks a, b, c in vector order for the query axis."""
    document = Document.create(filename="r.pdf")
    await PostgresDocumentRepository(db_pool).create(document)
    texts = ["a", "b", "c"]
    embeddings = [
        [math.cos(0.2 * i), math.sin(0.2 * i)] + [0.0] * (_DIM - 2)
        for i in range(3)
    ]
    await PostgresChunkRepository(db_pool, _DIM).replace_document_chunks(
        document.id,
        [Chunk.create(document.id, i, t) for i, t in enumerate(texts)],
        embeddings,
    )


@pytest.mark.integration
@respx.mock
async def test_search_with_rerank_model_configured_returns_reranked_order(
    pg_dsn: str, db_pool: PostgresPool
) -> None:
    await _seed_three_chunks(db_pool)
    respx.post(f"{_OLLAMA}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [_QUERY]})
    )
    respx.post(f"{_OLLAMA}/api/generate").mock(
        side_effect=[
            rerank_reply({"yes": 0.1, "no": 0.9}),
            rerank_reply({"yes": 0.9, "no": 0.1}),
            rerank_reply({"yes": 0.5, "no": 0.5}),
        ]
    )
    container = create_container(
        Settings(
            _env_file=None,
            postgres_dsn=pg_dsn,
            embedding_dim=_DIM,
            ollama_base_url=_OLLAMA,
            ollama_rerank_model="reranker",
        )
    )

    await container.startup()
    try:
        results = await container.search_chunks.execute("q", top_k=2)
    finally:
        await container.shutdown()

    assert [result.text for result in results] == ["b", "c"]


@pytest.mark.integration
@respx.mock
async def test_search_without_rerank_model_never_calls_the_reranker(
    pg_dsn: str, db_pool: PostgresPool
) -> None:
    await _seed_three_chunks(db_pool)
    respx.post(f"{_OLLAMA}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [_QUERY]})
    )
    generate = respx.post(f"{_OLLAMA}/api/generate")
    container = create_container(
        Settings(
            _env_file=None,
            postgres_dsn=pg_dsn,
            embedding_dim=_DIM,
            ollama_base_url=_OLLAMA,
        )
    )

    await container.startup()
    try:
        results = await container.search_chunks.execute("q", top_k=2)
    finally:
        await container.shutdown()

    assert ([r.text for r in results], generate.called) == (["a", "b"], False)
