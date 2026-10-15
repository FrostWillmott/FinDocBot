"""Shared fakes for use-case tests."""

from __future__ import annotations

import math

import httpx

from findocbot.domain.entities import Chunk
from findocbot.use_cases.ingestion import IngestionUseCase
from tests.in_memory import InMemoryChunkRepository


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


class ScriptedReranker:
    """Scores a passage from a lookup table and records what it was asked."""

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        self.calls.append((query, list(passages)))
        return [self._scores[passage] for passage in passages]


async def chunks_in_vector_order(texts: list[str]) -> InMemoryChunkRepository:
    """A repository whose vector order for StubProvider's query is *texts*."""
    repository = InMemoryChunkRepository()
    chunks = [
        Chunk.create("doc", index, text) for index, text in enumerate(texts)
    ]
    angles = [0.2 * index for index in range(len(texts))]
    embeddings = [[math.cos(a), math.sin(a), 0.0] for a in angles]
    await repository.replace_document_chunks("doc", chunks, embeddings)
    return repository


def rerank_reply(probabilities: dict[str, float]) -> httpx.Response:
    """An /api/generate reply whose first token has these probabilities."""
    top = [
        {"token": token, "logprob": math.log(p)}
        for token, p in probabilities.items()
    ]
    return httpx.Response(
        200,
        json={
            "response": "",
            "logprobs": [{"token": "x", "logprob": 0.0, "top_logprobs": top}],
        },
    )
