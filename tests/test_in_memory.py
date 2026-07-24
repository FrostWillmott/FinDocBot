"""Edge cases for in-memory repository adapters."""

from findocbot.domain.entities import Chunk
from findocbot.infrastructure.in_memory import InMemoryChunkRepository


async def test_search_by_embedding_zero_vector_returns_zero_score() -> None:
    repo = InMemoryChunkRepository()
    chunk = Chunk.create(document_id="doc-1", chunk_index=0, text="hello")
    await repo.add_chunks_with_embeddings([chunk], [[1.0, 2.0, 3.0]])

    results = await repo.search_by_embedding([0.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].score == 0.0
