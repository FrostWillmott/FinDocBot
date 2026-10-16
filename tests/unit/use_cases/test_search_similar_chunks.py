from __future__ import annotations

import asyncio
import logging

import pytest

from findocbot.domain.exceptions import (
    EmbeddingInputTooLongError,
    InvalidQueryError,
    ModelProviderError,
)
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.ingestion import IngestionUseCase
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from tests.factories import build_pdf_bytes
from tests.fakes import (
    ScriptedReranker,
    StubProvider,
    chunks_in_vector_order,
    index_document,
)
from tests.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
)


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

    ingestion = IngestionUseCase(
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
    await index_document(ingestion, "report.pdf", pdf_bytes)

    results = await search.execute(query="What about revenue?", top_k=1)

    assert results
    assert "Revenue" in results[0].text


async def test_execute_blank_query_raises_invalid_query() -> None:
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(), chunks=InMemoryChunkRepository()
    )
    with pytest.raises(InvalidQueryError):
        await search.execute(query="  ", top_k=3)


async def test_execute_with_reranker_returns_top_k_by_reranker_score() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c", "d"])
    reranker = ScriptedReranker({"a": 0.1, "b": 0.9, "c": 0.5, "d": 0.7})
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=chunks,
        reranker=reranker,
        rerank_candidates=4,
    )

    results = await search.execute(query="q", top_k=2)

    assert [result.text for result in results] == ["b", "d"]


async def test_execute_with_reranker_without_matches_does_not_call_it() -> (
    None
):
    reranker = ScriptedReranker({})
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=InMemoryChunkRepository(),
        reranker=reranker,
    )

    results = await search.execute(query="q", top_k=3)

    assert (results, reranker.calls) == ([], [])


class _FailingReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        raise ModelProviderError("reranker model is not pulled")


async def test_execute_reranker_failure_falls_back_to_vector_order() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c", "d"])
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=chunks,
        reranker=_FailingReranker(),
        rerank_candidates=4,
    )

    results = await search.execute(query="q", top_k=2)

    assert [result.text for result in results] == ["a", "b"]


async def test_execute_reranker_failure_is_logged_with_its_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    chunks = await chunks_in_vector_order(["a", "b"])
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(), chunks=chunks, reranker=_FailingReranker()
    )

    with caplog.at_level(logging.WARNING):
        await search.execute(query="q", top_k=1)

    assert "reranker model is not pulled" in caplog.text


async def test_execute_with_reranker_reports_the_reranker_score() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c"])
    reranker = ScriptedReranker({"a": 0.1, "b": 0.9, "c": 0.5})
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(), chunks=chunks, reranker=reranker
    )

    results = await search.execute(query="q", top_k=2)

    assert [result.score for result in results] == [0.9, 0.5]


class _NeverAnsweringReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        await asyncio.Event().wait()
        return []


async def test_execute_slow_reranker_falls_back_to_vector_order() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c"])
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=chunks,
        reranker=_NeverAnsweringReranker(),
        rerank_timeout_seconds=0.01,
    )

    results = await search.execute(query="q", top_k=2)

    assert [result.text for result in results] == ["a", "b"]


async def test_execute_with_reranker_scores_only_the_candidate_pool() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c", "d", "e"])
    reranker = ScriptedReranker(dict.fromkeys("abcde", 0.5))
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=chunks,
        reranker=reranker,
        rerank_candidates=3,
    )

    await search.execute(query="q", top_k=2)

    assert reranker.calls == [("q", ["a", "b", "c"])]


async def test_execute_with_reranker_never_pools_fewer_than_top_k() -> None:
    chunks = await chunks_in_vector_order(["a", "b", "c", "d"])
    reranker = ScriptedReranker(dict.fromkeys("abcd", 0.5))
    search = SearchSimilarChunksUseCase(
        provider=StubProvider(),
        chunks=chunks,
        reranker=reranker,
        rerank_candidates=2,
    )

    results = await search.execute(query="q", top_k=3)

    assert len(results) == 3


class _QueryTooLongProvider(StubProvider):
    async def embed_one(self, text: str) -> list[float]:
        raise EmbeddingInputTooLongError("An input is longer than 8192 tokens")


async def test_execute_query_over_the_window_raises_invalid_query() -> None:
    use_case = SearchSimilarChunksUseCase(
        provider=_QueryTooLongProvider(), chunks=InMemoryChunkRepository()
    )

    with pytest.raises(InvalidQueryError, match="Query is too long"):
        await use_case.execute("a very long question", top_k=3)
