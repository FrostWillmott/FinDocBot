"""Full-stack end-to-end: real Postgres + real Ollama through the HTTP API."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = (
    _REPO_ROOT / "docs" / "samples" / "aurora-ridge-annual-report-2025.pdf"
)


async def _wait_until_ready(
    client: httpx.AsyncClient, document_id: str
) -> dict[str, object]:
    for _ in range(60):
        response = await client.get(f"/documents/{document_id}")
        body = response.json()
        if body["status"] in ("ready", "failed"):
            return body
        await asyncio.sleep(1)
    raise AssertionError("document did not reach ready/failed within 60s")


@pytest.mark.e2e
async def test_upload_search_ask_end_to_end(
    client: httpx.AsyncClient,
) -> None:
    # Both real systems answer the health probe.
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["checks"] == {
        "database": "ok",
        "model_provider": "ok",
    }

    # Upload a real PDF; ingestion runs on the background worker.
    upload = await client.post(
        "/documents/upload",
        files={
            "file": (
                "aurora-ridge.pdf",
                _SAMPLE_PDF.read_bytes(),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 202
    document_id = upload.json()["document_id"]

    document = await _wait_until_ready(client, document_id)
    assert document["status"] == "ready"

    # Search retrieves the embedded chunks.
    search = await client.post(
        "/search", json={"query": "total revenue", "top_k": 3}
    )
    assert search.status_code == 200
    chunks = search.json()
    assert chunks, "expected at least one retrieved chunk"
    assert all(chunk["text"] for chunk in chunks)

    # Ask returns a structured answer citing the retrieved sources.
    ask = await client.post(
        "/ask", json={"question": "What was the total revenue?", "top_k": 3}
    )
    assert ask.status_code == 200
    answer = ask.json()
    assert answer["answer"]
    assert answer["confidence"] in {"high", "medium", "low"}
    assert answer["sources"], "expected cited sources"
    assert answer["session_id"]
