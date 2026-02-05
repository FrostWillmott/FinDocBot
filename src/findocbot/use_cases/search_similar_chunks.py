"""Search chunks by query use case."""

from findocbot.domain.exceptions import InvalidQueryError
from findocbot.use_cases.dto import SearchResultDTO
from findocbot.use_cases.ports import ChunkRepositoryPort, ModelProviderGateway


class SearchSimilarChunksUseCase:
    """Find most relevant chunks for a user query."""

    def __init__(
        self,
        provider: ModelProviderGateway,
        chunks: ChunkRepositoryPort,
    ) -> None:
        """Store dependencies for semantic retrieval."""
        self._provider = provider
        self._chunks = chunks

    async def execute(self, query: str, top_k: int) -> list[SearchResultDTO]:
        """Embed query and return matching chunks."""
        clean_query = query.strip()
        if not clean_query:
            raise InvalidQueryError("Query cannot be empty.")

        query_embedding = await self._provider.embed_one(clean_query)
        matches = await self._chunks.search_by_embedding(
            query_embedding, top_k=top_k
        )
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
