"""API error-path tests: use-case exceptions map to HTTP status codes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from fpdf import FPDF

from findocbot.config import Settings
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.container import AppContainer
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.main import create_app
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.ingestion import IngestionUseCase
from findocbot.use_cases.manage_documents import ManageDocumentsUseCase
from findocbot.use_cases.ports import ChunkWithScore
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from tests.factories import build_pdf_bytes
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    InMemoryHistoryRepository,
    SignallingDocumentRepository,
)


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


class _NumericAnswerProvider(_StubProvider):
    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        return {"answer": 42, "confidence": "high"}


class _FailingSearchChunkRepository(InMemoryChunkRepository):
    async def search_by_embedding(
        self, embedding: list[float], top_k: int
    ) -> list[ChunkWithScore]:
        raise StorageError("database unavailable")


class _FirstEmbedBreaksProvider(_StubProvider):
    """Raises a non-domain error on the first ingestion, then works."""

    def __init__(self) -> None:
        self._broken = True

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if self._broken:
            self._broken = False
            raise RuntimeError("boom")
        return await super().embed_many(texts)


def _build_container(
    provider: _StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
    health_checks: dict[str, Callable[[], Awaitable[None]]] | None = None,
    documents: InMemoryDocumentRepository | None = None,
) -> AppContainer:
    provider = provider if provider is not None else _StubProvider()
    chunks = chunks if chunks is not None else InMemoryChunkRepository()
    documents = (
        documents if documents is not None else InMemoryDocumentRepository()
    )
    history = InMemoryHistoryRepository()

    search_chunks = SearchSimilarChunksUseCase(
        provider=provider, chunks=chunks
    )
    answer_question = AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search_chunks,
        history=history,
    )
    ingestion = IngestionUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider,
        documents=documents,
        chunks=chunks,
    )
    return AppContainer(
        settings=Settings(),
        db=_FakeDB(),  # type: ignore[arg-type]
        provider=provider,
        ingestion=ingestion,
        search_chunks=search_chunks,
        answer_question=answer_question,
        manage_documents=ManageDocumentsUseCase(documents),
        health_checks=health_checks or {},
    )


def _build_app(
    provider: _StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
    health_checks: dict[str, Callable[[], Awaitable[None]]] | None = None,
) -> httpx.ASGITransport:
    container = _build_container(
        provider=provider, chunks=chunks, health_checks=health_checks
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
        assert resp.json()["detail"] == "Model provider request failed."


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


async def test_upload_blank_pdf_marks_document_failed_after_processing() -> (
    None
):
    container = _build_container()
    pdf = FPDF()
    pdf.add_page()
    blank_pdf = bytes(pdf.output())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(container=container)),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("blank.pdf", blank_pdf, "application/pdf")},
        )
        assert resp.status_code == 202
        document_id = resp.json()["document_id"]

        await container.ingestion.drain()

        stored = await client.get(f"/documents/{document_id}")
        assert stored.json()["status"] == "failed"
        assert "does not contain text" in stored.json()["error"]


async def test_upload_non_pdf_bytes_marks_document_failed() -> None:
    container = _build_container()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(container=container)),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        assert resp.status_code == 202
        document_id = resp.json()["document_id"]

        await container.ingestion.drain()

        stored = await client.get(f"/documents/{document_id}")
        assert stored.json()["status"] == "failed"
        assert "not a readable PDF" in stored.json()["error"]


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


async def test_ask_non_string_answer_returns_502() -> None:
    transport = _build_app(provider=_NumericAnswerProvider())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post("/ask", json={"question": "revenue?"})
        assert resp.status_code == 502


async def _passing_check() -> None:
    pass


async def _failing_check() -> None:
    raise ModelProviderError("Ollama unreachable")


async def test_health_failing_check_returns_503_naming_it() -> None:
    transport = _build_app(
        health_checks={
            "database": _passing_check,
            "model_provider": _failing_check,
        }
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert (resp.status_code, resp.json()) == (
            503,
            {
                "status": "degraded",
                "checks": {"database": "ok", "model_provider": "unavailable"},
            },
        )


async def test_ask_unknown_session_id_returns_404() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/ask", json={"session_id": "guessed-id", "question": "revenue?"}
        )
        assert resp.status_code == 404


async def test_ask_returned_session_id_is_accepted_on_next_call() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        first = await client.post("/ask", json={"question": "revenue?"})
        resp = await client.post(
            "/ask",
            json={
                "session_id": first.json()["session_id"],
                "question": "and profit?",
            },
        )
        assert resp.status_code == 200


async def _upload_pdf(client: httpx.AsyncClient) -> httpx.Response:
    pdf = build_pdf_bytes("Revenue grew.")
    return await client.post(
        "/documents/upload", files={"file": ("r.pdf", pdf, "application/pdf")}
    )


async def test_documents_after_upload_lists_it() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        upload = await _upload_pdf(client)
        resp = await client.get("/documents")
        assert [item["document_id"] for item in resp.json()] == [
            upload.json()["document_id"]
        ]


async def test_delete_document_then_get_returns_404() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        upload = await _upload_pdf(client)
        url = f"/documents/{upload.json()['document_id']}"
        deleted = await client.delete(url)
        resp = await client.get(url)
        assert (deleted.status_code, resp.status_code) == (204, 404)


async def test_delete_unknown_document_returns_404() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/documents/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404


async def test_get_document_malformed_id_returns_422() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        resp = await client.get("/documents/not-a-uuid")
        assert resp.status_code == 422


async def test_get_document_after_upload_returns_its_filename() -> None:
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        upload = await _upload_pdf(client)
        resp = await client.get(f"/documents/{upload.json()['document_id']}")
        assert resp.json()["filename"] == "r.pdf"


async def test_upload_duplicate_of_pending_document_responds_200_same_id() -> (
    None
):
    async with httpx.AsyncClient(
        transport=_build_app(), base_url="http://test"
    ) as client:
        first = await _upload_pdf(client)
        second = await _upload_pdf(client)

        assert (second.status_code, second.json()["document_id"]) == (
            200,
            first.json()["document_id"],
        )


async def test_upload_duplicate_of_pending_document_is_ingested_once() -> None:
    chunks = InMemoryChunkRepository()
    container = _build_container(chunks=chunks)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(container=container)),
        base_url="http://test",
    ) as client:
        await _upload_pdf(client)
        await _upload_pdf(client)

        await container.ingestion.drain()

    # The one-paragraph PDF is a single chunk, so a second ingestion would
    # show up as a second stored chunk.
    assert len(chunks.items) == 1


async def test_upload_unexpected_ingestion_error_marks_document_failed() -> (
    None
):
    documents = SignallingDocumentRepository()
    container = _build_container(
        provider=_FirstEmbedBreaksProvider(), documents=documents
    )
    await container.startup()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(container=container)),
            base_url="http://test",
        ) as client:
            broken = await _upload_pdf(client)
            # The second upload becoming ready shows the worker survived.
            await client.post(
                "/documents/upload",
                files={
                    "file": (
                        "p.pdf",
                        build_pdf_bytes("Profit fell."),
                        "application/pdf",
                    )
                },
            )
            await asyncio.wait_for(documents.ready.wait(), timeout=5)

            stored = await client.get(
                f"/documents/{broken.json()['document_id']}"
            )
    finally:
        await container.shutdown()

    assert (stored.json()["status"], stored.json()["error"]) == (
        "failed",
        "Ingestion failed unexpectedly.",
    )
