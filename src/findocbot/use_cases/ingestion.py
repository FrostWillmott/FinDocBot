"""Ingestion use case: accept an upload and ingest it in the background."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass

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
)

logger = logging.getLogger(__name__)

# Fixed, not a setting: nothing about it varies per deployment. A full queue
# makes ``submit`` wait, which holds the upload request open.
_QUEUE_MAXSIZE = 100

# Stored as the document's ``error`` when ingestion fails for a reason we did
# not anticipate; the cause (driver or parser internals) goes to the log only.
_UNEXPECTED_ERROR_MESSAGE = "Ingestion failed unexpectedly."

# What a document says after the process holding its queued bytes went away.
# Uploading again is a real remedy: a duplicate of a failed document is
# retried.
_INTERRUPTED_MESSAGE = "Ingestion was interrupted by a restart; upload again."


@dataclass(frozen=True)
class _Job:
    document_id: str
    content: bytes


@dataclass(frozen=True)
class Submission:
    """Outcome of ``IngestionUseCase.submit``."""

    document: Document
    # True when this request queued ingestion: a new upload, or the retry of a
    # failed document. False when the bytes resolved to a document that is
    # pending or ready, or whose retry another request claimed first.
    queued: bool


def _safe_error_message(error: FinDocBotError) -> str:
    """Return a client-safe message for an ingestion failure.

    ``ModelProviderError`` can name Ollama's internal URL, which a client
    has no use for; every other failure carries user-facing text already.
    """
    if isinstance(error, ModelProviderError):
        return "Model provider request failed."
    return str(error)


class IngestionUseCase:
    """Accept uploaded PDFs and ingest them into searchable chunks.

    ``submit`` stores a ``pending`` document and queues its bytes; one worker
    parses, chunks, embeds and persists them, then marks the document
    ``ready`` or ``failed``. Queued bytes live in memory, so jobs not yet
    handled do not survive a restart; ``recover_interrupted`` then marks their
    documents ``failed`` at startup. That assumes a single API instance (see
    DECISIONS.md).
    """

    def __init__(
        self,
        parser: PDFParserPort,
        chunker: ChunkerPort,
        provider: ModelProviderGateway,
        documents: DocumentRepositoryPort,
        chunks: ChunkRepositoryPort,
    ) -> None:
        """Store dependencies for the ingestion workflow."""
        self._parser = parser
        self._chunker = chunker
        self._provider = provider
        self._documents = documents
        self._chunks = chunks
        self._queue: asyncio.Queue[_Job] = asyncio.Queue(
            maxsize=_QUEUE_MAXSIZE
        )
        self._worker: asyncio.Task[None] | None = None

    async def submit(self, filename: str, content: bytes) -> Submission:
        """Register an upload and queue it for background ingestion.

        A new upload returns a ``pending`` document with ``queued=True``; the
        worker flips it to ``ready`` or ``failed`` after processing.
        Re-uploading the same bytes returns the stored document with
        ``queued=False`` and does not queue it again, so uploads stay
        idempotent and cost no extra parsing or embedding, except that a
        ``failed`` document is retried: it goes back to ``pending`` and is
        queued again (``queued=True``).
        """
        content_hash = hashlib.sha256(content).hexdigest()
        existing = await self._documents.find_by_content_hash(content_hash)
        if existing is not None:
            return await self._resubmit(existing, content)

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
            return Submission(document=stored, queued=False)
        await self._queue.put(_Job(document_id=document.id, content=content))
        return Submission(document=document, queued=True)

    async def _resubmit(
        self, existing: Document, content: bytes
    ) -> Submission:
        """Retry a failed document; return any other stored one as it is."""
        if existing.status != "failed":
            return Submission(document=existing, queued=False)
        claimed = await self._documents.reset_failed(existing.id)
        if claimed is None:
            # Another request claimed the retry first (or the document was
            # deleted meanwhile): show the row as it is now.
            current = await self._documents.get(existing.id)
            return Submission(document=current or existing, queued=False)
        await self._queue.put(_Job(document_id=claimed.id, content=content))
        return Submission(document=claimed, queued=True)

    async def recover_interrupted(self) -> None:
        """Mark documents left pending by a previous process as failed.

        Run once at startup, before the worker starts: a pending document
        then has no job anywhere (the queue was in memory), so it would stay
        pending for ever. Uploading the same bytes again retries it.
        """
        count = await self._documents.fail_pending(_INTERRUPTED_MESSAGE)
        if count:
            logger.warning(
                "Marked %d document(s) interrupted by a restart as failed",
                count,
            )

    async def start(self) -> None:
        """Spawn the worker task if it is not already running."""
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the worker; unprocessed jobs are dropped (not durable)."""
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    async def drain(self) -> None:
        """Process every queued job to completion (used by tests)."""
        while not self._queue.empty():
            job = await self._queue.get()
            await self._process(job)
            self._queue.task_done()

    async def _run(self) -> None:
        """Consume jobs until cancelled."""
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            except Exception:
                # Last resort: ``_process`` already records every failure it
                # can, so this only sees one it could not (for example the
                # status update itself raising). An unexpected bug must not
                # kill the worker; log it and keep processing.
                logger.exception(
                    "Upload worker failed on job %s", job.document_id
                )
            finally:
                self._queue.task_done()

    async def _process(self, job: _Job) -> None:
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
            await self._mark_failed(job, _safe_error_message(error), error)
        except Exception as error:
            # Deliberately broad: this is the outermost boundary of a
            # background job with no caller to report to, and a driver or
            # parser bug must not leave the document 'pending' for ever. The
            # traceback is logged; the client sees only a fixed message.
            logger.exception(
                "Unexpected error ingesting document %s", job.document_id
            )
            await self._mark_failed(job, _UNEXPECTED_ERROR_MESSAGE, error)

    async def _mark_failed(
        self, job: _Job, message: str, cause: Exception
    ) -> None:
        """Store a failure on the document; log if even that cannot be done."""
        try:
            await self._documents.set_status(
                job.document_id, "failed", message
            )
        except FinDocBotError:
            # The database is unavailable too; nothing can record the
            # failure, so log it and let the worker move on.
            logger.exception(
                "Could not record ingestion failure for %s: %s",
                job.document_id,
                cause,
            )

    async def _ingest(self, job: _Job) -> None:
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
        await self._chunks.replace_document_chunks(
            job.document_id, built_chunks, embeddings
        )
