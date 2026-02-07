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


class FakeProviderGateway:
    async def embed_one(self, text: str) -> list[float]:
        return self._encode(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    async def generate(self, prompt: str) -> str:
        if "revenue" in prompt.lower():
            return "Revenue growth is 20 percent according to the report."
        return "Insufficient context."

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


async def test_answer_generation_contains_keywords() -> None:
    provider = FakeProviderGateway()
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1)
    docs = InMemoryDocumentRepository()
    chunks = InMemoryChunkRepository()
    history = InMemoryHistoryRepository()

    upload = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=docs,
        chunks=chunks,
    )
    search = SearchSimilarChunksUseCase(provider=provider, chunks=chunks)
    ask = AnswerQuestionUseCase(
        provider=provider,
        search_use_case=search,
        history=history,
    )

    pdf_bytes = _build_pdf_bytes("Revenue grew by 20 percent in the quarter.")
    await upload.execute("report.pdf", pdf_bytes)

    response = await ask.execute(
        session_id="session-1",
        question="How did revenue change?",
        top_k=2,
    )

    assert "revenue" in response.answer.lower()
    assert "20 percent" in response.answer.lower()
