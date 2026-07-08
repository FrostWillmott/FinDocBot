"""Smoke tests that verify app wiring through the HTTP layer.

Catches regressions like forgotten pass-through methods (C2) and ensures
the container can be built with fake dependencies.
"""

import httpx
from fpdf import FPDF

from findocbot.config import Settings
from findocbot.infrastructure.cached_embedding_gateway import (
    CachedEmbeddingGateway,
)
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
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase


class _FakeDB:
    """Minimal pool stub for smoke tests that do not touch PostgreSQL."""

    @property
    def pool(self) -> None:
        raise RuntimeError("DB must not be accessed in smoke tests")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _FakeModelProvider:
    """In-memory provider that returns deterministic embeddings and answers."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def embed_one(self, text: str) -> list[float]:
        return self._encode(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(t) for t in texts]

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        if "revenue" in prompt.lower():
            return {
                "answer": "Revenue grew by 20 percent.",
                "confidence": "high",
            }
        return {"answer": "Insufficient context.", "confidence": "low"}

    @staticmethod
    def _encode(text: str) -> list[float]:
        lower = text.lower()
        return [
            float(lower.count("revenue")),
            float(lower.count("profit")),
            float(lower.count("assets")),
        ]


def _build_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    data = pdf.output()
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, bytes):
        return data
    return data.encode("latin-1")


def _build_test_container() -> AppContainer:
    """Wire an AppContainer with in-memory dependencies for smoke testing."""
    settings = Settings()
    fake_db = _FakeDB()
    provider = _FakeModelProvider()
    cached_provider = CachedEmbeddingGateway(
        gateway=provider,
        cache_size=10,
    )
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1)
    chunks = InMemoryChunkRepository()
    documents = InMemoryDocumentRepository()
    history = InMemoryHistoryRepository()

    search_chunks = SearchSimilarChunksUseCase(
        provider=cached_provider, chunks=chunks
    )
    answer_question = AnswerQuestionUseCase(
        provider=cached_provider,
        search_use_case=search_chunks,
        history=history,
    )
    upload_pdf = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=cached_provider,
        documents=documents,
        chunks=chunks,
    )

    return AppContainer(
        settings=settings,
        db=fake_db,  # type: ignore[arg-type]
        provider=cached_provider,
        upload_pdf=upload_pdf,
        search_chunks=search_chunks,
        answer_question=answer_question,
    )


async def test_health_endpoint_returns_ok() -> None:
    """Smoke: /health responds with status ok."""
    app = create_app(container=_build_test_container())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


async def test_ask_endpoint_with_uploaded_pdf() -> None:
    """Smoke: upload a PDF then ask a question — full use-case wiring."""
    container = _build_test_container()
    app = create_app(container=container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        # Upload a PDF first to have chunks indexed.
        pdf_bytes = _build_pdf_bytes(
            "Revenue grew by 20 percent in the last quarter. "
            "Operating profit remained stable."
        )
        upload_resp = await client.post(
            "/documents/upload",
            files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        assert "document_id" in upload_data

        # Ask a question that should match the uploaded content.
        ask_resp = await client.post(
            "/ask",
            json={
                "session_id": "smoke-session",
                "question": "How did revenue change?",
                "top_k": 3,
            },
        )
        assert ask_resp.status_code == 200
        ask_data = ask_resp.json()
        assert "answer" in ask_data
        assert "confidence" in ask_data
        assert len(ask_data["sources"]) > 0


async def test_upload_rejects_non_pdf_content_type() -> None:
    """Smoke: non-PDF content type returns a client error."""
    app = create_app(container=_build_test_container())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("doc.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400


async def test_ask_rejects_empty_question() -> None:
    """Smoke: empty question returns a client error."""
    app = create_app(container=_build_test_container())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/ask",
            json={
                "session_id": "session-1",
                "question": "",
                "top_k": 3,
            },
        )
        assert resp.status_code == 422  # Pydantic validation error
