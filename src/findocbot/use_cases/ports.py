"""Abstractions for use-case dependencies."""

from dataclasses import dataclass
from typing import Protocol

from findocbot.domain.entities import ChatTurn, Chunk, Document


@dataclass(frozen=True)
class ChunkWithScore:
    """Chunk and similarity score."""

    chunk: Chunk
    score: float


class PDFParserPort(Protocol):
    """Extract plain text from PDF bytes."""

    def extract_text(self, content: bytes) -> str:
        """Return extracted text."""


class ChunkerPort(Protocol):
    """Split extracted text into semantic chunks."""

    def split(self, text: str) -> list[tuple[str, str | None]]:
        """Return tuples of chunk text and optional section label."""


class ModelProviderGateway(Protocol):
    """Model provider abstraction for embeddings and generation."""

    async def embed_one(self, text: str) -> list[float]:
        """Embed single text query."""

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts in one call."""

    async def generate(self, prompt: str) -> str:
        """Generate model response from prompt."""


class DocumentRepositoryPort(Protocol):
    """Persistence operations for documents."""

    async def create(self, document: Document) -> None:
        """Persist a document."""


class ChunkRepositoryPort(Protocol):
    """Persistence operations for chunks with vectors."""

    async def add_chunks_with_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Persist chunks with embeddings."""

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Return top-k similar chunks."""


class ChatHistoryRepositoryPort(Protocol):
    """Persistence operations for Q/A history."""

    async def add_turn(self, turn: ChatTurn) -> None:
        """Persist chat turn."""

    async def list_recent(
        self,
        session_id: str,
        limit: int,
    ) -> list[ChatTurn]:
        """Return recent turns ordered from oldest to newest."""
