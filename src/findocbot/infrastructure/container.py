"""Dependency container wiring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
from findocbot.infrastructure.upload_queue import InProcessUploadQueue
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.manage_documents import ManageDocumentsUseCase
from findocbot.use_cases.ports import ModelProviderGateway
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass
class AppContainer:
    """Top-level dependency holder."""

    settings: Settings
    db: PostgresPool
    provider: ModelProviderGateway
    upload_pdf: UploadPDFUseCase
    search_chunks: SearchSimilarChunksUseCase
    answer_question: AnswerQuestionUseCase
    manage_documents: ManageDocumentsUseCase
    upload_queue: InProcessUploadQueue
    # Run after the database is up; a failure aborts application startup.
    startup_checks: list[Callable[[], Awaitable[None]]] = field(
        default_factory=list
    )
    # Run by /health; each raises InfrastructureError when its system is down.
    health_checks: dict[str, Callable[[], Awaitable[None]]] = field(
        default_factory=dict
    )

    async def startup(self) -> None:
        """Initialize external resources and run startup checks."""
        await self.db.start()
        for check in self.startup_checks:
            await check()
        await self.provider.start()
        await self.upload_queue.start()

    async def shutdown(self) -> None:
        """Shutdown external resources."""
        await self.upload_queue.stop()
        await self.provider.stop()
        await self.db.stop()


def create_container(settings: Settings) -> AppContainer:
    """Wire use-cases with concrete infrastructure implementations."""
    db = PostgresPool(
        str(settings.postgres_dsn), max_size=settings.db_pool_max_size
    )
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(
        chunk_tokens=settings.chunk_tokens,
        overlap_ratio=settings.chunk_overlap_ratio,
    )

    ollama_gateway = OllamaGateway(
        base_url=settings.ollama_base_url,
        chat_model=settings.ollama_chat_model,
        embed_model=settings.ollama_embed_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        batch_size=settings.embedding_batch_size,
        num_ctx=settings.ollama_num_ctx,
        num_predict=settings.ollama_num_predict,
    )
    provider = CachedEmbeddingGateway(
        gateway=ollama_gateway,
        cache_size=settings.embedding_cache_size,
        ttl_seconds=settings.embedding_cache_ttl_seconds,
    )

    documents = PostgresDocumentRepository(db)
    chunks = PostgresChunkRepository(db, settings.embedding_dim)
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
    upload_queue = InProcessUploadQueue()
    upload_pdf = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=documents,
        chunks=chunks,
        queue=upload_queue,
    )
    upload_queue.set_processor(upload_pdf.process)

    return AppContainer(
        settings=settings,
        db=db,
        provider=provider,
        upload_pdf=upload_pdf,
        search_chunks=search_chunks,
        answer_question=answer_question,
        manage_documents=ManageDocumentsUseCase(documents),
        upload_queue=upload_queue,
        startup_checks=[chunks.verify_schema],
        health_checks={
            "database": db.ping,
            "model_provider": ollama_gateway.ping,
        },
    )
