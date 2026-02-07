from fpdf import FPDF

from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.in_memory import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
)
from findocbot.infrastructure.pdf_parser import PyPDFParser
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
        return prompt

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


async def test_upload_then_search_returns_relevant_chunk() -> None:
    provider = FakeProviderGateway()
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(chunk_tokens=120, overlap_ratio=0.1)
    docs = InMemoryDocumentRepository()
    chunks = InMemoryChunkRepository()

    upload = UploadPDFUseCase(
        parser=parser,
        chunker=chunker,
        provider=provider,
        documents=docs,
        chunks=chunks,
    )
    search = SearchSimilarChunksUseCase(provider=provider, chunks=chunks)

    pdf_bytes = _build_pdf_bytes(
        "Section 1\nRevenue grew by 20 percent.\n\n"
        "Section 2\nOperational profit remained stable.\n\n"
        "Section 3\nAsset quality improved."
    )
    await upload.execute("report.pdf", pdf_bytes)

    results = await search.execute(query="What about revenue?", top_k=1)

    assert results
    assert "Revenue" in results[0].text
