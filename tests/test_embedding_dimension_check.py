from __future__ import annotations

import pytest

from findocbot.domain.entities import Chunk
from findocbot.domain.exceptions import EmbeddingDimensionError
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChunkRepository,
)


@pytest.fixture
def repo() -> PostgresChunkRepository:
    # The pool is never started: the check must fire before any DB access.
    return PostgresChunkRepository(PostgresPool("postgresql://unused"), 3)


async def test_insert_wrong_dimension_raises_before_db_access(
    repo: PostgresChunkRepository,
) -> None:
    chunk = Chunk.create(document_id="d", chunk_index=0, text="x")

    with pytest.raises(EmbeddingDimensionError, match="has 2 dimensions"):
        await repo.add_chunks_with_embeddings([chunk], [[0.1, 0.2]])


async def test_search_wrong_dimension_raises_before_db_access(
    repo: PostgresChunkRepository,
) -> None:
    with pytest.raises(EmbeddingDimensionError, match="EMBEDDING_DIM is 3"):
        await repo.search_by_embedding([0.1] * 4, top_k=1)
