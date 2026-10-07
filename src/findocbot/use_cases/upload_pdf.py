"""Upload PDF use case."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from findocbot.domain.entities import Chunk, Document
from findocbot.domain.exceptions import (
    DuplicateDocumentError,
    EmptyDocumentError,
    FinDocBotError,
    ModelProviderError,
)
from findocbot.use_cases.ports import (
    ChunkerPort,
    ChunkRepositoryPort,
    DocumentRepositoryPort,
    ModelProviderGateway,
    PDFParserPort,
    UploadJob,
    UploadQueuePort,
)

logger = logging.getLogger(__name__)


def _safe_error_message(error: FinDocBotError) -> str:
    """Return a client-safe message for an ingestion failure.

    ``ModelProviderError`` can name Ollama's internal URL, which a client
    has no use for; every other failure carries user-facing text already.
    """
    if isinstance(error, ModelProviderError):
        return "Model provider request failed."
    return str(error)


class UploadPDFUseCase:
    """Extract, chunk, embed, and save an uploaded PDF in the background."""

    def __init__(
        self,
        parser: PDFParserPort,
        chunker: ChunkerPort,
        provider: ModelProviderGateway,
        documents: DocumentRepositoryPort,
        chunks: ChunkRepositoryPort,
        queue: UploadQueuePort,
    ) -> None:
        """Store dependencies for the upload workflow."""
        self._parser = parser
        self._chunker = chunker
        self._provider = provider
        self._documents = documents
        self._chunks = chunks
        self._queue = queue

    async def submit(self, filename: str, content: bytes) -> Document:
        """Register an upload and queue it for background ingestion.

        Returns a document with ``status="pending"``; the worker flips it to
        ``ready`` or ``failed`` after processing. Re-uploading the same bytes
        returns the stored document without queueing it again, so uploads
        stay idempotent and cost no extra parsing or embedding.
        """
        content_hash = hashlib.sha256(content).hexdigest()
        existing = await self._documents.find_by_content_hash(content_hash)
        if existing is not None:
            return existing

        document = Document.create(
            filename=filename,
            content_hash=content_hash,
            status="pending",
        )
        try:
            await self._documents.create(document)
        except DuplicateDocumentError:
            # A concurrent upload of the same bytes was stored first.
            stored = await self._documents.find_by_content_hash(content_hash)
            if stored is None:
                raise
            return stored
        await self._queue.enqueue(
            UploadJob(
                document_id=document.id,
                filename=filename,
                content=content,
            )
        )
        return document

    async def process(self, job: UploadJob) -> None:
        """Parse, chunk, embed, and persist one queued upload.

        CPU-bound PDF parsing and chunking are offloaded to a thread so they
        do not block the event loop. Any failure marks the document
        ``failed`` with a client-safe message, so ``GET /documents/{id}``
        explains why it never became searchable.
        """
        try:
            await self._ingest(job)
            await self._documents.set_status(job.document_id, "ready")
        except FinDocBotError as error:
            try:
                await self._documents.set_status(
                    job.document_id, "failed", _safe_error_message(error)
                )
            except FinDocBotError:
                # The database is unavailable too; nothing can record the
                # failure, so log it and let the worker move on.
                logger.exception(
                    "Could not record ingestion failure for %s: %s",
                    job.document_id,
                    error,
                )

    async def _ingest(self, job: UploadJob) -> None:
        """Run the parse → chunk → embed → persist pipeline for one upload."""
        text = (
            await asyncio.to_thread(self._parser.extract_text, job.content)
        ).strip()
        if not text:
            raise EmptyDocumentError("Uploaded PDF does not contain text.")

        chunk_parts = await asyncio.to_thread(self._chunker.split, text)
        built_chunks = [
            Chunk.create(
                document_id=job.document_id,
                chunk_index=index,
                text=chunk_text,
                section=section,
            )
            for index, (chunk_text, section) in enumerate(chunk_parts)
            if chunk_text.strip()
        ]

        embeddings = await self._provider.embed_many([
            c.text for c in built_chunks
        ])
        await self._chunks.add_chunks_with_embeddings(built_chunks, embeddings)
