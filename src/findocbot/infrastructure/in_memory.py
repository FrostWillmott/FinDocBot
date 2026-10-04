"""In-memory adapters used in tests and local dry runs."""

from __future__ import annotations

from dataclasses import dataclass

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
)
from findocbot.domain.exceptions import DuplicateDocumentError
from findocbot.use_cases.ports import ChunkWithScore


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    numerator = float(sum(x * y for x, y in zip(a, b, strict=True)))
    a_norm: float = sum(x * x for x in a) ** 0.5
    b_norm: float = sum(y * y for y in b) ** 0.5
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return numerator / (a_norm * b_norm)


class InMemoryDocumentRepository:
    """Simple document repository for tests."""

    def __init__(self) -> None:
        """Initialize in-memory document storage."""
        self.items: dict[str, Document] = {}

    async def create(self, document: Document) -> None:
        """Store document entity."""
        if (
            document.content_hash is not None
            and await self.find_by_content_hash(document.content_hash)
        ):
            raise DuplicateDocumentError("Document already exists")
        self.items[document.id] = document

    async def find_by_content_hash(self, content_hash: str) -> Document | None:
        """Return the document stored with this content hash, if any."""
        return next(
            (
                item
                for item in self.items.values()
                if item.content_hash == content_hash
            ),
            None,
        )

    async def get(self, document_id: str) -> Document | None:
        """Return the document with this id, if any."""
        return self.items.get(document_id)

    async def list_page(self, limit: int, offset: int) -> list[Document]:
        """Return documents, newest first."""
        newest_first = sorted(
            self.items.values(), key=lambda item: item.created_at, reverse=True
        )
        return newest_first[offset : offset + limit]

    async def delete(self, document_id: str) -> bool:
        """Remove document entity by id; return whether it existed."""
        return self.items.pop(document_id, None) is not None


@dataclass
class _StoredChunk:
    chunk: Chunk
    embedding: list[float]


class InMemoryChunkRepository:
    """Simple chunk repository for tests."""

    def __init__(self) -> None:
        """Initialize in-memory chunk storage."""
        self.items: list[_StoredChunk] = []

    async def add_chunks_with_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Store chunks with their embedding vectors."""
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self.items.append(_StoredChunk(chunk=chunk, embedding=embedding))

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Return top-k chunks sorted by cosine similarity."""
        ranked = sorted(
            self.items,
            key=lambda item: _cosine_similarity(item.embedding, embedding),
            reverse=True,
        )[:top_k]
        return [
            ChunkWithScore(
                chunk=entry.chunk,
                score=_cosine_similarity(entry.embedding, embedding),
            )
            for entry in ranked
        ]


class InMemoryHistoryRepository:
    """Simple chat history repository for tests."""

    def __init__(self) -> None:
        """Initialize in-memory chat history."""
        self.items: list[ChatTurn] = []
        self.session_ids: set[str] = set()

    async def create_session(self, session: ChatSession) -> None:
        """Record an issued session."""
        self.session_ids.add(session.id)

    async def session_exists(self, session_id: str) -> bool:
        """Return whether the session was issued."""
        return session_id in self.session_ids

    async def add_turn(self, turn: ChatTurn) -> None:
        """Append one turn to history."""
        self.items.append(turn)

    async def list_recent(self, session_id: str, limit: int) -> list[ChatTurn]:
        """Return latest turns for the session."""
        filtered = [
            item for item in self.items if item.session_id == session_id
        ]
        return filtered[-limit:]
