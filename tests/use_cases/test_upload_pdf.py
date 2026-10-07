"""Tests for UploadPDFUseCase."""

from __future__ import annotations

import hashlib

from fpdf import FPDF

from findocbot.domain.entities import Document
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.upload_pdf import UploadPDFUseCase
from tests.factories import build_pdf_bytes
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
)
from tests.use_cases.fakes import RecordingQueue, StubProvider


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


def _build_upload(
    *,
    documents: InMemoryDocumentRepository | None = None,
    provider: StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
    queue: RecordingQueue | None = None,
) -> tuple[UploadPDFUseCase, RecordingQueue, InMemoryDocumentRepository]:
    queue = queue if queue is not None else RecordingQueue()
    documents = (
        documents if documents is not None else InMemoryDocumentRepository()
    )
    upload = UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider or StubProvider(),
        documents=documents,
        chunks=chunks or InMemoryChunkRepository(),
        queue=queue,
    )
    return upload, queue, documents


async def test_submit_creates_pending_document_and_enqueues_job() -> None:
    upload, queue, documents = _build_upload()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    document = await upload.submit("report.pdf", pdf_bytes)

    assert document.status == "pending"
    assert documents.items[document.id].status == "pending"
    assert len(queue.jobs) == 1
    assert queue.jobs[0].document_id == document.id
    assert queue.jobs[0].content == pdf_bytes


async def test_submit_same_bytes_twice_returns_first_and_enqueues_once() -> (
    None
):
    upload, queue, documents = _build_upload()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    first = await upload.submit("report.pdf", pdf_bytes)
    second = await upload.submit("report-copy.pdf", pdf_bytes)

    assert second == first
    assert len(queue.jobs) == 1
    assert list(documents.items) == [first.id]


async def test_submit_concurrent_duplicate_returns_stored_document() -> None:
    documents = _RacingDocumentRepository()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    stored = Document.create(
        filename="report.pdf",
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
    )
    # Seeded directly: create() would spend the pre-check miss itself.
    documents.items[stored.id] = stored
    upload, queue, _ = _build_upload(documents=documents)

    result = await upload.submit("report.pdf", pdf_bytes)

    assert (result, len(queue.jobs)) == (stored, 0)


async def test_process_marks_document_ready_and_stores_chunks() -> None:
    chunks = InMemoryChunkRepository()
    upload, queue, documents = _build_upload(chunks=chunks)
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await upload.submit("report.pdf", pdf_bytes)

    await upload.process(queue.jobs[0])

    stored = documents.items[document.id]
    assert stored.status == "ready"
    assert stored.error is None
    assert chunks.items


async def test_process_empty_pdf_marks_document_failed() -> None:
    upload, queue, documents = _build_upload()
    pdf = FPDF()
    pdf.add_page()
    blank = bytes(pdf.output())
    document = await upload.submit("blank.pdf", blank)

    await upload.process(queue.jobs[0])

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert "does not contain text" in (stored.error or "")


async def test_process_chunk_storage_failure_marks_document_failed() -> None:
    upload, queue, documents = _build_upload(chunks=_FailingChunkRepository())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await upload.submit("report.pdf", pdf_bytes)

    await upload.process(queue.jobs[0])

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "insert failed"


async def test_process_provider_failure_sanitizes_error_message() -> None:
    upload, queue, documents = _build_upload(provider=_FailingProvider())
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    document = await upload.submit("report.pdf", pdf_bytes)

    await upload.process(queue.jobs[0])

    stored = documents.items[document.id]
    assert stored.status == "failed"
    assert stored.error == "Model provider request failed."
