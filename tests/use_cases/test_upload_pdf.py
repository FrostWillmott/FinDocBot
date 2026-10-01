"""Tests for UploadPDFUseCase."""

from __future__ import annotations

import pytest

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
