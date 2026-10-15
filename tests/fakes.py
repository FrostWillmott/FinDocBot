"""Shared fakes for use-case tests."""

from __future__ import annotations

from findocbot.use_cases.ingestion import IngestionUseCase


class StubProvider:
    """Fake provider with a configurable structured response."""

    def __init__(self, structured: dict | None = None) -> None:
        self.structured = structured or {
            "answer": "ok",
            "confidence": "high",
        }

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def embed_one(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        return self.structured


async def index_document(
    ingestion: IngestionUseCase, filename: str, content: bytes
) -> None:
    """Submit one upload and ingest it synchronously for test setup.

    Mirrors the production flow minus the background worker: submit returns
    a pending document, then ``drain`` runs the pipeline to completion.
    """
    await ingestion.submit(filename, content)
    await ingestion.drain()
