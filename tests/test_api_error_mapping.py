"""API error-path tests: use-case exceptions map to HTTP status codes."""

import httpx
from fpdf import FPDF

from findocbot.config import Settings
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.container import AppContainer
from findocbot.infrastructure.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    InMemoryHistoryRepository,
)
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.main import create_app
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.ports import ChunkWithScore
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase


class _FakeDB:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _StubProvider:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def embed_one(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        return {"answer": "ok", "confidence": "low"}


class _FailingEmbedProvider(_StubProvider):
    async def embed_one(self, text: str) -> list[float]:
        raise ModelProviderError("Ollama is down")


class _FailingSearchChunkRepository(InMemoryChunkRepository):
    async def search_by_embedding(
        self, embedding: list[float], top_k: int
    ) -> list[ChunkWithScore]:
        raise StorageError("database unavailable")


def _build_app(
    provider: _StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
) -> httpx.ASGITransport:
    provider = provider if provider is not None else _StubProvider()
    chunks = chunks if chunks is not None else InMemoryChunkRepository()
    documents = InMemoryDocumentRepository()
    history = InMemoryHistoryRepository()

    search_chunks = SearchSimilarChunksUseCase(
        provider=provider, chunks=chunks
    )
    answer_question = AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search_chunks,
        history=history,
    )
    upload_pdf = UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider,
        documents=documents,
        chunks=chunks,
    )
    container = AppContainer(
        settings=Settings(),
        db=_FakeDB(),  # type: ignore[arg-type]
        provider=provider,
        upload_pdf=upload_pdf,
        search_chunks=search_chunks,
        answer_question=answer_question,
    )
    return httpx.ASGITransport(app=create_app(container=container))


async def test_search_empty_index_returns_empty_list() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/search", json={"query": "revenue", "top_k": 3}
        )
        assert resp.status_code == 200
        assert resp.json() == []


async def test_search_provider_failure_returns_502() -> None:
    transport = _build_app(provider=_FailingEmbedProvider())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/search", json={"query": "revenue", "top_k": 3}
        )
        assert resp.status_code == 502
        assert "Ollama is down" in resp.json()["detail"]


async def test_search_storage_failure_returns_503() -> None:
    transport = _build_app(chunks=_FailingSearchChunkRepository())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/search", json={"query": "revenue", "top_k": 3}
        )
        assert resp.status_code == 503
        assert "database unavailable" in resp.json()["detail"]


async def test_upload_pdf_without_text_returns_400() -> None:
    pdf = FPDF()
    pdf.add_page()
    blank_pdf = bytes(pdf.output())

    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("blank.pdf", blank_pdf, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "does not contain text" in resp.json()["detail"]


async def test_upload_oversized_file_returns_413() -> None:
    oversized = b"0" * (50 * 1024 * 1024 + 1)
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("big.pdf", oversized, "application/pdf")},
        )
        assert resp.status_code == 413
        assert "50 MB" in resp.json()["detail"]
