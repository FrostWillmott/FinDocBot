"""Tests for IngestionUseCase."""

from __future__ import annotations

import asyncio
import hashlib
import logging

import pytest
from fpdf import FPDF

from findocbot.domain.entities import Document, DocumentStatus
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.ingestion import IngestionUseCase
from tests.factories import build_pdf_bytes
from tests.fakes import StubProvider
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    SignallingDocumentRepository,
)


class _FailingChunkRepository(InMemoryChunkRepository):
    async def add_chunks_with_embeddings(
        self,
        chunks: list,
        embeddings: list[list[float]],
    ) -> None:
        raise StorageError("insert failed")


class _FailingProvider(StubProvider):
    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise ModelProviderError("Ollama unreachable at http://internal")


class _BuggyProvider(StubProvider):
    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("asyncpg internals at /srv/app/db.py")


class _UnrecordableFailureRepository(InMemoryDocumentRepository):
    """Fails to store a 'failed' status, as if the database went away."""

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        if status == "failed":
            raise StorageError("database unavailable")
        await super().set_status(document_id, status, error)


class _BrokenFailureRepository(SignallingDocumentRepository):
    """Raises a non-domain error when asked to store a 'failed' status."""

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        if status == "failed":
            raise RuntimeError("status update broke")
        await super().set_status(document_id, status, error)


class _RacingDocumentRepository(InMemoryDocumentRepository):
    """Misses the hash on the pre-check, as if a concurrent upload of the
    same bytes was stored between the check and the insert."""

    def __init__(self) -> None:
        super().__init__()
        self._misses_left = 1

    async def find_by_content_hash(self, content_hash: str) -> Document | None:
        if self._misses_left:
            self._misses_left -= 1
            return None
        return await super().find_by_content_hash(content_hash)


def _build_ingestion(
    *,
    documents: InMemoryDocumentRepository | None = None,
    provider: StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
) -> tuple[IngestionUseCase, InMemoryDocumentRepository]:
    documents = (
        documents if documents is not None else InMemoryDocumentRepository()
    )
    ingestion = IngestionUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider or StubProvider(),
        documents=documents,
        chunks=chunks or InMemoryChunkRepository(),
    )
    return ingestion, documents


async def _submit(
    ingestion: IngestionUseCase, filename: str, content: bytes
) -> Document:
    return (await ingestion.submit(filename, content)).document


async def test_submit_new_upload_creates_pending_document() -> None:
    ingestion, documents = _build_ingestion()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    document = await _submit(ingestion, "report.pdf", pdf_bytes)

    assert (document.status, documents.items[document.id].status) == (
        "pending",
        "pending",
    )


async def test_submit_same_bytes_twice_returns_first_and_ingests_once() -> (
    None
):
    chunks = InMemoryChunkRepository()
    ingestion, documents = _build_ingestion(chunks=chunks)
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    first = await _submit(ingestion, "report.pdf", pdf_bytes)
    second = await _submit(ingestion, "report-copy.pdf", pdf_bytes)
    await ingestion.drain()

    # The one-paragraph PDF is a single chunk, so a second ingestion would
    # show up as a second stored chunk.
    assert (second, list(documents.items), len(chunks.items)) == (
        first,
        [first.id],
        1,
    )


async def test_submit_same_bytes_twice_queues_only_the_first() -> None:
    ingestion, _ = _build_ingestion()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    first = await ingestion.submit("report.pdf", pdf_bytes)
    second = await ingestion.submit("report-copy.pdf", pdf_bytes)

    assert (first.queued, second.queued) == (True, False)


async def test_submit_concurrent_duplicate_returns_stored_document() -> None:
    documents = _RacingDocumentRepository()
    chunks = InMemoryChunkRepository()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    stored = Document.create(
        filename="report.pdf",
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
    )
    # Seeded directly: create() would spend the pre-check miss itself.
    documents.items[stored.id] = stored
    ingestion, _ = _build_ingestion(documents=documents, chunks=chunks)

    result = await ingestion.submit("report.pdf", pdf_bytes)
    await ingestion.drain()

    assert (result.document, result.queued, len(chunks.items)) == (
        stored,
        False,
        0,
    )


async def test_drain_upload_marks_document_ready_and_stores_chunks() -> None:
    chunks = InMemoryChunkRepository()
    ingestion, documents = _build_ingestion(chunks=chunks)
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await _submit(ingestion, "report.pdf", pdf_bytes)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "ready"
    assert stored.error is None
    assert chunks.items


async def test_drain_empty_pdf_marks_document_failed() -> None:
    ingestion, documents = _build_ingestion()
    pdf = FPDF()
    pdf.add_page()
    blank = bytes(pdf.output())
    document = await _submit(ingestion, "blank.pdf", blank)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert "does not contain text" in (stored.error or "")


async def test_drain_chunk_storage_failure_marks_document_failed() -> None:
    ingestion, documents = _build_ingestion(chunks=_FailingChunkRepository())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await _submit(ingestion, "report.pdf", pdf_bytes)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "insert failed"


async def test_drain_provider_failure_sanitizes_error_message() -> None:
    ingestion, documents = _build_ingestion(provider=_FailingProvider())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await _submit(ingestion, "report.pdf", pdf_bytes)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "Model provider request failed."


async def test_drain_unexpected_error_marks_document_failed() -> None:
    ingestion, documents = _build_ingestion(provider=_BuggyProvider())
    document = await _submit(
        ingestion, "report.pdf", build_pdf_bytes("Revenue grew by 20 percent.")
    )

    await ingestion.drain()

    stored = documents.items[document.id]
    # The exact text also shows the error's own message did not leak.
    assert (stored.status, stored.error) == (
        "failed",
        "Ingestion failed unexpectedly.",
    )


async def test_drain_unexpected_error_logs_the_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ingestion, _ = _build_ingestion(provider=_BuggyProvider())
    await _submit(
        ingestion, "report.pdf", build_pdf_bytes("Revenue grew by 20 percent.")
    )

    with caplog.at_level(logging.ERROR):
        await ingestion.drain()

    # The log is the only place the cause survives.
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [
        RuntimeError
    ]


async def test_drain_failure_that_cannot_be_recorded_is_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ingestion, _ = _build_ingestion(
        documents=_UnrecordableFailureRepository(), provider=_FailingProvider()
    )
    document = await _submit(
        ingestion, "report.pdf", build_pdf_bytes("Revenue grew by 20 percent.")
    )

    with caplog.at_level(logging.ERROR):
        await ingestion.drain()

    assert f"Could not record ingestion failure for {document.id}" in (
        caplog.text
    )


async def test_worker_unrecordable_failure_keeps_processing_next_job() -> None:
    documents = _BrokenFailureRepository()
    ingestion, _ = _build_ingestion(documents=documents)
    pdf = FPDF()
    pdf.add_page()
    await _submit(ingestion, "blank.pdf", bytes(pdf.output()))
    second = await _submit(
        ingestion, "report.pdf", build_pdf_bytes("Revenue grew by 20 percent.")
    )

    await ingestion.start()
    try:
        await asyncio.wait_for(documents.ready.wait(), timeout=5)
    finally:
        await ingestion.stop()

    assert documents.items[second.id].status == "ready"
