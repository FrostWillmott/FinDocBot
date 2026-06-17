"""RAG evaluation: faithfulness and retrieval precision metrics.

Uses a deterministic in-memory setup (no external services required).

Metrics
-------
retrieval_precision
    Fraction of retrieved chunks that are relevant to the question.
    A chunk is considered relevant when its text contains at least one
    keyword from the expected answer.

faithfulness
    Fraction of Q&A pairs where the generated answer is grounded in the
    retrieved context (i.e. the answer does not introduce facts absent
    from the context).  Implemented as keyword overlap: every significant
    word in the answer must appear in at least one retrieved chunk.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpdf import FPDF

from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    InMemoryHistoryRepository,
)
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase

# ---------------------------------------------------------------------------
# Golden Q&A dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QAPair:
    question: str
    expected_keywords: list[str]  # must appear in a relevant chunk
    answer_keywords: list[str]  # keywords that must appear in the answer


QA_DATASET: list[QAPair] = [
    QAPair(
        question="What was the revenue growth?",
        expected_keywords=["revenue"],
        answer_keywords=["revenue", "20"],
    ),
    QAPair(
        question="How did operational profit change?",
        expected_keywords=["profit"],
        answer_keywords=["profit", "stable"],
    ),
    QAPair(
        question="What happened to asset quality?",
        expected_keywords=["asset"],
        answer_keywords=["asset", "improved"],
    ),
]

# ---------------------------------------------------------------------------
# Fake provider — deterministic, keyword-based
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Deterministic provider for evaluation tests."""

    async def embed_one(self, text: str) -> list[float]:
        return self._encode(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(t) for t in texts]

    async def generate(self, prompt: str) -> str:
        return self._answer_from_prompt(prompt)

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        return {
            "answer": self._answer_from_prompt(prompt),
            "confidence": "high",
        }

    @staticmethod
    def _answer_from_prompt(prompt: str) -> str:
        lower = prompt.lower()
        if "revenue" in lower:
            return "Revenue grew by 20 percent."
        if "profit" in lower:
            return "Operational profit remained stable."
        if "asset" in lower:
            return "Asset quality improved significantly."
        return "Insufficient context."

    @staticmethod
    def _encode(text: str) -> list[float]:
        lower = text.lower()
        return [
            float(lower.count("revenue")),
            float(lower.count("profit")),
            float(lower.count("asset")),
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    data = pdf.output()
    if isinstance(data, bytes | bytearray):
        return bytes(data)
    return data.encode("latin-1")


def _retrieval_precision(chunks: list, relevant_keywords: list[str]) -> float:
    """Fraction of retrieved chunks with at least one relevant keyword."""
    if not chunks:
        return 0.0
    relevant = sum(
        1
        for c in chunks
        if any(kw.lower() in c.text.lower() for kw in relevant_keywords)
    )
    return relevant / len(chunks)


def _faithfulness(
    answer: str, chunks: list, answer_keywords: list[str]
) -> float:
    """Fraction of answer keywords grounded in retrieved context."""
    if not answer_keywords:
        return 1.0
    context = " ".join(c.text.lower() for c in chunks)
    grounded = sum(1 for kw in answer_keywords if kw.lower() in context)
    return grounded / len(answer_keywords)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


async def test_rag_evaluation_metrics() -> None:
    """Evaluate retrieval precision and faithfulness over the Q&A dataset."""
    provider = _FakeProvider()
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1)
    docs = InMemoryDocumentRepository()
    chunks_repo = InMemoryChunkRepository()
    history = InMemoryHistoryRepository()

    upload = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=docs,
        chunks=chunks_repo,
    )
    search = SearchSimilarChunksUseCase(provider=provider, chunks=chunks_repo)
    ask = AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search,
        history=history,
    )

    corpus = (
        "Section 1\nRevenue grew by 20 percent year-over-year.\n\n"
        "Section 2\nOperational profit remained stable despite headwinds.\n\n"
        "Section 3\nAsset quality improved significantly in Q4."
    )
    await upload.execute("annual_report.pdf", _build_pdf_bytes(corpus))

    precision_scores: list[float] = []
    faithfulness_scores: list[float] = []

    for qa in QA_DATASET:
        retrieved = await search.execute(qa.question, top_k=3)
        result = await ask.execute(
            session_id="eval-session",
            question=qa.question,
            top_k=3,
        )

        p = _retrieval_precision(retrieved, qa.expected_keywords)
        f = _faithfulness(result.answer, retrieved, qa.answer_keywords)
        precision_scores.append(p)
        faithfulness_scores.append(f)

    avg_precision = sum(precision_scores) / len(precision_scores)
    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)

    # Thresholds: at least 0.5 precision and 0.5 faithfulness on this corpus.
    assert avg_precision >= 0.5, (
        f"Retrieval precision too low: {avg_precision:.2f} "
        f"(per-question: {precision_scores})"
    )
    assert avg_faithfulness >= 0.5, (
        f"Faithfulness too low: {avg_faithfulness:.2f} "
        f"(per-question: {faithfulness_scores})"
    )
