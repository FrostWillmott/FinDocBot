"""Full-stack end-to-end: real Postgres + real Ollama through the HTTP API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = (
    _REPO_ROOT / "docs" / "samples" / "aurora-ridge-annual-report-2025.pdf"
)
# The sample's "Financial Highlights" section states this revenue figure; it
# is how the tests tell a correct retrieval from "some chunk came back".
_REPORTED_REVENUE = "1,284"
_INGESTION_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Ingestion:
    upload_status: int
    document: dict[str, object]


async def _wait_until_settled(
    client: httpx.AsyncClient, document_id: str
) -> dict[str, object]:
    """Poll until the worker has made the document ready or failed."""
    for _ in range(_INGESTION_TIMEOUT_SECONDS):
        response = await client.get(f"/documents/{document_id}")
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        if body["status"] != "pending":
            return body
        await asyncio.sleep(1)
    raise AssertionError(
        f"document did not settle within {_INGESTION_TIMEOUT_SECONDS}s"
    )


async def _wait_until_ready(
    client: httpx.AsyncClient, document_id: str
) -> dict[str, object]:
    body = await _wait_until_settled(client, document_id)
    # The worker stores a client-safe reason; show it, it is the only clue a
    # CI failure leaves.
    assert body["status"] == "ready", f"ingestion failed: {body['error']}"
    return body


@pytest.fixture
def sample_pdf() -> bytes:
    return _SAMPLE_PDF.read_bytes()


@pytest.fixture
async def ingestion(client: httpx.AsyncClient, sample_pdf: bytes) -> Ingestion:
    """Upload the sample PDF and wait until the worker has embedded it."""
    upload = await client.post(
        "/documents/upload",
        files={"file": ("aurora-ridge.pdf", sample_pdf, "application/pdf")},
    )
    assert upload.is_success, upload.text
    document = await _wait_until_ready(client, upload.json()["document_id"])
    return Ingestion(upload_status=upload.status_code, document=document)


@pytest.mark.e2e
async def test_health_real_postgres_and_ollama_reports_both_ok(
    client: httpx.AsyncClient,
) -> None:
    health = await client.get("/health")

    assert health.json()["checks"] == {
        "database": "ok",
        "model_provider": "ok",
    }


@pytest.mark.e2e
async def test_upload_sample_pdf_new_document_responds_202_accepted(
    ingestion: Ingestion,
) -> None:
    assert ingestion.upload_status == 202


@pytest.mark.e2e
async def test_upload_sample_pdf_background_worker_marks_document_ready(
    ingestion: Ingestion,
) -> None:
    assert ingestion.document["status"] == "ready"


@pytest.mark.e2e
async def test_search_total_revenue_after_ingestion_returns_reported_figure(
    client: httpx.AsyncClient, ingestion: Ingestion
) -> None:
    search = await client.post(
        "/search", json={"query": "total revenue", "top_k": 3}
    )
    assert search.status_code == 200, search.text

    assert any(_REPORTED_REVENUE in chunk["text"] for chunk in search.json())


@pytest.mark.e2e
async def test_ask_total_revenue_after_ingestion_cites_reported_figure(
    client: httpx.AsyncClient, ingestion: Ingestion
) -> None:
    ask = await client.post(
        "/ask", json={"question": "What was the total revenue?", "top_k": 3}
    )
    assert ask.status_code == 200, ask.text

    # Only the sources are asserted: retrieval is deterministic, the text a
    # 0.5B model samples at Ollama's default temperature is not.
    assert any(
        _REPORTED_REVENUE in source["text"] for source in ask.json()["sources"]
    )


@pytest.mark.e2e
async def test_upload_chunk_over_the_embedding_window_fails_the_document(
    narrow_window_client: httpx.AsyncClient, sample_pdf: bytes
) -> None:
    upload = await narrow_window_client.post(
        "/documents/upload",
        files={"file": ("aurora-ridge.pdf", sample_pdf, "application/pdf")},
    )

    document = await _wait_until_settled(
        narrow_window_client, upload.json()["document_id"]
    )

    assert (document["status"], document["error"]) == (
        "failed",
        (
            "A passage of the document is too long for the embedding model; "
            "the server's chunk size or embedding window needs adjusting."
        ),
    )


@pytest.mark.e2e
async def test_search_query_over_the_embedding_window_responds_400(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/search", json={"query": "revenue " * 12000, "top_k": 3}
    )

    assert (response.status_code, response.json()["detail"]) == (
        400,
        "Query is too long.",
    )
