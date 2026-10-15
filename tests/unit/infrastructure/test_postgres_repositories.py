"""Dimension-guard checks on the Postgres repositories (no DB access).

The repository validates embedding dimensions before touching the database,
so these checks run with a pool that is never started.
"""

from __future__ import annotations

import pytest

from findocbot.domain.entities import Chunk
from findocbot.domain.exceptions import EmbeddingDimensionError
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChunkRepository,
)


@pytest.fixture
def unstarted_repo() -> PostgresChunkRepository:
    # The pool is never started: the check must fire before any DB access.
    return PostgresChunkRepository(PostgresPool("postgresql://unused"), 3)


async def test_chunk_insert_wrong_dim_raises_without_db_access(
    unstarted_repo: PostgresChunkRepository,
) -> None:
    chunk = Chunk.create(document_id="d", chunk_index=0, text="x")

    with pytest.raises(EmbeddingDimensionError, match="has 2 dimensions"):
        await unstarted_repo.replace_document_chunks(
            "d", [chunk], [[0.1, 0.2]]
        )


async def test_chunk_search_wrong_dim_raises_without_db_access(
    unstarted_repo: PostgresChunkRepository,
) -> None:
    with pytest.raises(EmbeddingDimensionError, match="EMBEDDING_DIM is 3"):
        await unstarted_repo.search_by_embedding([0.1] * 4, top_k=1)
