"""Tests for IngestionUseCase."""

from __future__ import annotations

import hashlib

from fpdf import FPDF

from findocbot.domain.entities import Document
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.ingestion import IngestionUseCase
from tests.factories import build_pdf_bytes
from tests.fakes import StubProvider
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
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


async def test_submit_new_upload_creates_pending_document() -> None:
    ingestion, documents = _build_ingestion()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    document = await ingestion.submit("report.pdf", pdf_bytes)

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

    first = await ingestion.submit("report.pdf", pdf_bytes)
    second = await ingestion.submit("report-copy.pdf", pdf_bytes)
    await ingestion.drain()

    # The one-paragraph PDF is a single chunk, so a second ingestion would
    # show up as a second stored chunk.
    assert (second, list(documents.items), len(chunks.items)) == (
        first,
        [first.id],
        1,
    )


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

    assert (result, len(chunks.items)) == (stored, 0)


async def test_drain_upload_marks_document_ready_and_stores_chunks() -> None:
    chunks = InMemoryChunkRepository()
    ingestion, documents = _build_ingestion(chunks=chunks)
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await ingestion.submit("report.pdf", pdf_bytes)

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
    document = await ingestion.submit("blank.pdf", blank)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert "does not contain text" in (stored.error or "")


async def test_drain_chunk_storage_failure_marks_document_failed() -> None:
    ingestion, documents = _build_ingestion(chunks=_FailingChunkRepository())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await ingestion.submit("report.pdf", pdf_bytes)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "insert failed"


async def test_drain_provider_failure_sanitizes_error_message() -> None:
    ingestion, documents = _build_ingestion(provider=_FailingProvider())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await ingestion.submit("report.pdf", pdf_bytes)

    await ingestion.drain()

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "Model provider request failed."
