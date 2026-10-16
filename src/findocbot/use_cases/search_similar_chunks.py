"""Search chunks by query use case."""

from __future__ import annotations

import asyncio
import logging

from findocbot.domain.exceptions import (
    EmbeddingInputTooLongError,
    InvalidQueryError,
    ModelProviderError,
)
from findocbot.use_cases.dto import SearchResultDTO
from findocbot.use_cases.ports import (
    ChunkRepositoryPort,
    ChunkWithScore,
    ModelProviderGateway,
    RerankerPort,
)

logger = logging.getLogger(__name__)


class SearchSimilarChunksUseCase:
    """Find most relevant chunks for a user query."""

    def __init__(
        self,
        provider: ModelProviderGateway,
        chunks: ChunkRepositoryPort,
        reranker: RerankerPort | None = None,
        rerank_candidates: int = 20,
        rerank_timeout_seconds: float = 30.0,
    ) -> None:
        """Store dependencies for semantic retrieval."""
        self._provider = provider
        self._chunks = chunks
        self._reranker = reranker
        self._rerank_candidates = rerank_candidates
        self._rerank_timeout = rerank_timeout_seconds

    async def execute(self, query: str, top_k: int) -> list[SearchResultDTO]:
        """Embed query and return matching chunks."""
        clean_query = query.strip()
        if not clean_query:
            raise InvalidQueryError("Query cannot be empty.")

        try:
            query_embedding = await self._provider.embed_one(clean_query)
        except EmbeddingInputTooLongError as error:
            # The client's text is the cause, unlike any other embedding
            # failure, so say so instead of reporting a provider outage.
            raise InvalidQueryError("Query is too long.") from error
        pool = top_k
        if self._reranker is not None:
            pool = max(top_k, self._rerank_candidates)
        matches = await self._chunks.search_by_embedding(
            query_embedding, top_k=pool
        )
        if self._reranker is not None and matches:
            try:
                async with asyncio.timeout(self._rerank_timeout):
                    scores = await self._reranker.rerank(
                        clean_query, [item.chunk.text for item in matches]
                    )
            except (ModelProviderError, TimeoutError) as error:
                logger.warning(
                    "Reranking failed, keeping vector order: %r", error
                )
                matches = matches[:top_k]
            else:
                ranked = sorted(
                    zip(scores, matches, strict=True),
                    key=lambda pair: -pair[0],
                )[:top_k]
                matches = [
                    ChunkWithScore(chunk=item.chunk, score=score)
                    for score, item in ranked
                ]
        return [
            SearchResultDTO(
                chunk_id=item.chunk.id,
                document_id=item.chunk.document_id,
                chunk_index=item.chunk.chunk_index,
                text=item.chunk.text,
                score=item.score,
                section=item.chunk.section,
            )
            for item in matches
        ]
