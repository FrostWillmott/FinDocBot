"""Tests for UploadPDFUseCase."""

from __future__ import annotations

import hashlib

import pytest

from findocbot.domain.entities import Document
from findocbot.domain.exceptions import StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
)
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.upload_pdf import UploadPDFUseCase
from tests.factories import build_pdf_bytes
from tests.use_cases.fakes import StubProvider


class _FailingChunkRepository(InMemoryChunkRepository):
    async def add_chunks_with_embeddings(
        self,
        chunks: list,
        embeddings: list[list[float]],
    ) -> None:
        raise StorageError("insert failed")


async def test_execute_chunk_storage_failure_deletes_document() -> None:
    documents = InMemoryDocumentRepository()
    upload = UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=StubProvider(),
        documents=documents,
        chunks=_FailingChunkRepository(),
    )
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    with pytest.raises(StorageError):
        await upload.execute("report.pdf", pdf_bytes)

    assert documents.items == {}


class _CountingProvider(StubProvider):
    def __init__(self) -> None:
        super().__init__()
        self.embed_many_calls = 0

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.embed_many_calls += 1
        return await super().embed_many(texts)


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
    documents: InMemoryDocumentRepository | None = None,
    provider: StubProvider | None = None,
) -> UploadPDFUseCase:
    return UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider or StubProvider(),
        documents=documents or InMemoryDocumentRepository(),
        chunks=InMemoryChunkRepository(),
    )


async def test_execute_same_bytes_twice_returns_first_document() -> None:
    upload = _build_upload()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    first = await upload.execute("report.pdf", pdf_bytes)
    second = await upload.execute("report-copy.pdf", pdf_bytes)

    assert second == first


async def test_execute_same_bytes_twice_embeds_once() -> None:
    provider = _CountingProvider()
    upload = _build_upload(provider=provider)
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")

    await upload.execute("report.pdf", pdf_bytes)
    await upload.execute("report.pdf", pdf_bytes)

    assert provider.embed_many_calls == 1


async def test_execute_concurrent_duplicate_returns_stored_document() -> None:
    documents = _RacingDocumentRepository()
    pdf_bytes = build_pdf_bytes("Revenue grew by 20 percent.")
    stored = Document.create(
        filename="report.pdf",
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
    )
    # Seeded directly: create() would spend the pre-check miss itself.
    documents.items[stored.id] = stored
    upload = _build_upload(documents=documents)

    result = await upload.execute("report.pdf", pdf_bytes)

    assert (result, list(documents.items)) == (stored, [stored.id])
