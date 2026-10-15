"""API error-path tests: use-case exceptions map to HTTP status codes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from fpdf import FPDF

from findocbot.config import Settings
from findocbot.domain.exceptions import ModelProviderError, StorageError
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.container import AppContainer
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.infrastructure.upload_queue import InProcessUploadQueue
from findocbot.main import create_app
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.manage_documents import ManageDocumentsUseCase
from findocbot.use_cases.ports import ChunkWithScore
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase
from tests.factories import build_pdf_bytes
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    InMemoryHistoryRepository,
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


def _build_container(
    provider: _StubProvider | None = None,
    chunks: InMemoryChunkRepository | None = None,
    health_checks: dict[str, Callable[[], Awaitable[None]]] | None = None,
) -> AppContainer:
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
    upload_queue = InProcessUploadQueue()
    upload_pdf = UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=provider,
        documents=documents,
        chunks=chunks,
        queue=upload_queue,
    )
    upload_queue.set_processor(upload_pdf.process)
    return AppContainer(
        settings=Settings(),
        db=_FakeDB(),  # type: ignore[arg-type]
        provider=provider,
        upload_pdf=upload_pdf,
        search_chunks=search_chunks,
        answer_question=answer_question,
        manage_documents=ManageDocumentsUseCase(documents),
        upload_queue=upload_queue,
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

        await container.upload_queue.drain()

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

        await container.upload_queue.drain()

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
