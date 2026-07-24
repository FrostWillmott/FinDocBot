"""Use-case error paths: rollback, LLM-output fallback, empty inputs."""

import pytest
from fpdf import FPDF

from findocbot.domain.exceptions import InvalidQueryError, StorageError
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


class _Provider:
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


class _FailingChunkRepository(InMemoryChunkRepository):
    async def add_chunks_with_embeddings(
        self,
        chunks: list,
        embeddings: list[list[float]],
    ) -> None:
        raise StorageError("insert failed")


def _build_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    return bytes(pdf.output())


def _build_answer_use_case(provider: _Provider) -> AnswerQuestionUseCase:
    search = SearchSimilarChunksUseCase(
        provider=provider, chunks=InMemoryChunkRepository()
    )
    return AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search,
        history=InMemoryHistoryRepository(),
    )


async def test_upload_chunk_persistence_failure_deletes_document() -> None:
    documents = InMemoryDocumentRepository()
    upload = UploadPDFUseCase(
        parser=PyPDFParser(),
        chunker=ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1),
        provider=_Provider(),
        documents=documents,
        chunks=_FailingChunkRepository(),
    )
    pdf_bytes = _build_pdf_bytes("Revenue grew by 20 percent.")

    with pytest.raises(StorageError):
        await upload.execute("report.pdf", pdf_bytes)

    assert documents.items == {}


async def test_answer_question_empty_question_raises_invalid_query() -> None:
    ask = _build_answer_use_case(_Provider())
    with pytest.raises(InvalidQueryError):
        await ask.execute(session_id="s1", question="   ", top_k=3)


async def test_answer_question_malformed_llm_output_falls_back() -> None:
    provider = _Provider(
        structured={"answer": "Revenue grew.", "confidence": "definitely"}
    )
    ask = _build_answer_use_case(provider)

    response = await ask.execute(
        session_id="s1", question="How did revenue change?", top_k=3
    )

    assert response.answer == "Revenue grew."
    assert response.confidence == "medium"


async def test_search_empty_query_raises_invalid_query() -> None:
    search = SearchSimilarChunksUseCase(
        provider=_Provider(), chunks=InMemoryChunkRepository()
    )
    with pytest.raises(InvalidQueryError):
        await search.execute(query="  ", top_k=3)
