from __future__ import annotations

import pytest

from findocbot.domain.exceptions import InvalidQueryError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase
from tests.factories import build_pdf_bytes
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
)
from tests.use_cases.fakes import StubProvider


class FakeProviderGateway:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def embed_one(self, text: str) -> list[float]:
        return self._encode(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    @staticmethod
    def _encode(text: str) -> list[float]:
        lower = text.lower()
        return [
            float(lower.count("revenue")),
            float(lower.count("profit")),
            float(lower.count("assets")),
        ]


async def test_execute_after_upload_returns_matching_chunk_first() -> None:
    provider = FakeProviderGateway()
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1)
    docs = InMemoryDocumentRepository()
    chunks = InMemoryChunkRepository()

    upload = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=docs,
        chunks=chunks,
    )
    search = SearchSimilarChunksUseCase(provider=provider, chunks=chunks)

    pdf_bytes = build_pdf_bytes(
        "Section 1\nRevenue grew by 20 percent.\n\n"
        "Section 2\nOperational profit remained stable.\n\n"
        "Section 3\nAsset quality improved."
    )
    await upload.execute("report.pdf", pdf_bytes)

    results = await search.execute(query="What about revenue?", top_k=1)

    assert results
    assert "Revenue" in results[0].text


async def test_execute_blank_query_raises_invalid_query() -> None:
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(), chunks=InMemoryChunkRepository()
    )
    with pytest.raises(InvalidQueryError):
        await search.execute(query="  ", top_k=3)
