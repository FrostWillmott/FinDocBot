"""Abstractions for use-case dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
    DocumentStatus,
)


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

    async def start(self) -> None:
        """Initialize resources (optional no-op for stateless providers)."""

    async def stop(self) -> None:
        """Release resources (optional no-op for stateless providers)."""

    async def embed_one(self, text: str) -> list[float]:
        """Embed single text query."""

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts in one call."""

    async def generate_structured(
        self, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate a JSON-structured response matching the given schema."""


class DocumentRepositoryPort(Protocol):
    """Persistence operations for documents."""

    async def create(self, document: Document) -> None:
        """Persist a document; raise DuplicateDocumentError on same hash."""

    async def find_by_content_hash(self, content_hash: str) -> Document | None:
        """Return the document stored with this content hash, if any."""

    async def get(self, document_id: str) -> Document | None:
        """Return the document with this id, if any."""

    async def list_page(self, limit: int, offset: int) -> list[Document]:
        """Return documents, newest first."""

    async def delete(self, document_id: str) -> bool:
        """Remove a document and its chunks; return whether it existed."""

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        """Update a document's ingestion status and optional error message."""

    async def reset_failed(self, document_id: str) -> Document | None:
        """Mark a failed document pending again and clear its error.

        Atomic: of several concurrent callers only one gets the updated
        document; the others, and a call for a document that is not failed
        or does not exist, get None.
        """


class ChunkRepositoryPort(Protocol):
    """Persistence operations for chunks with vectors."""

    async def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Make these chunks, with embeddings, the document's only chunks.

        Atomic: any chunks the document already had are removed in the same
        transaction, so a retried ingestion never leaves two copies.
        """

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Return top-k similar chunks."""


class ChatHistoryRepositoryPort(Protocol):
    """Persistence operations for Q/A history."""

    async def create_session(self, session: ChatSession) -> None:
        """Persist a newly issued session."""

    async def session_exists(self, session_id: str) -> bool:
        """Return whether the session was issued."""

    async def add_turn(self, turn: ChatTurn) -> None:
        """Persist chat turn."""

    async def list_recent(
        self,
        session_id: str,
        limit: int,
    ) -> list[ChatTurn]:
        """Return recent turns ordered from oldest to newest."""
