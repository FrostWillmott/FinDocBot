"""Dependency container wiring."""

from dataclasses import dataclass

from findocbot.config import Settings
from findocbot.infrastructure.cached_embedding_gateway import (
    CachedEmbeddingGateway,
)
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.ollama_gateway import OllamaGateway
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.infrastructure.postgres_repositories import (
    PostgresChatHistoryRepository,
    PostgresChunkRepository,
    PostgresDocumentRepository,
)
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase


@dataclass
class AppContainer:
    """Top-level dependency holder."""

    settings: Settings
    db: PostgresPool
    provider: CachedEmbeddingGateway
    upload_pdf: UploadPDFUseCase
    search_chunks: SearchSimilarChunksUseCase
    answer_question: AnswerQuestionUseCase

    async def startup(self) -> None:
        """Initialize external resources."""
        await self.db.start()
        await self.provider.start()

    async def shutdown(self) -> None:
        """Shutdown external resources."""
        await self.provider.stop()
        await self.db.stop()


def create_container(settings: Settings) -> AppContainer:
    """Wire use-cases with concrete infrastructure implementations."""
    db = PostgresPool(settings.postgres_dsn)
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=300, overlap_ratio=0.15)
    
    # Create Ollama gateway and wrap with caching layer
    ollama_gateway = OllamaGateway(
        base_url=settings.ollama_base_url,
        chat_model=settings.ollama_chat_model,
        embed_model=settings.ollama_embed_model,
        batch_size=settings.embedding_batch_size,
    )
    provider = CachedEmbeddingGateway(
        gateway=ollama_gateway,
        cache_size=settings.embedding_cache_size,
        ttl_seconds=settings.embedding_cache_ttl_seconds,
    )
    
    documents = PostgresDocumentRepository(db)
    chunks = PostgresChunkRepository(db)
    history = PostgresChatHistoryRepository(db)

    search_chunks = SearchSimilarChunksUseCase(
        provider=provider, chunks=chunks
    )
    answer_question = AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search_chunks,
        history=history,
        max_history_pairs=settings.max_history_pairs,
    )
    upload_pdf = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=documents,
        chunks=chunks,
    )

    return AppContainer(
        settings=settings,
        db=db,
        provider=provider,
        upload_pdf=upload_pdf,
        search_chunks=search_chunks,
        answer_question=answer_question,
    )
