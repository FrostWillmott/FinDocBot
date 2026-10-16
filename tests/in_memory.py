"""In-memory repository fakes for tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
    DocumentStatus,
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
    """Simple document repository for tests.

    ``chunks`` is set by ``in_memory_repositories``: deleting a document then
    removes its chunks, as the foreign key does in Postgres.
    """

    def __init__(self) -> None:
        """Initialize in-memory document storage."""
        self.items: dict[str, Document] = {}
        self.chunks: InMemoryChunkRepository | None = None

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
        existed = self.items.pop(document_id, None) is not None
        if existed and self.chunks is not None:
            self.chunks.remove_document(document_id)
        return existed

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        """Update a stored document's status and error message.

        An id that is not stored (deleted meanwhile) changes nothing, as the
        ``UPDATE`` in Postgres.
        """
        document = self.items.get(document_id)
        if document is not None:
            self.items[document_id] = replace(
                document, status=status, error=error
            )

    async def reset_failed(self, document_id: str) -> Document | None:
        """Mark a failed document pending again; None if it was not failed."""
        document = self.items.get(document_id)
        if document is None or document.status != "failed":
            return None
        reset = replace(document, status="pending", error=None)
        self.items[document_id] = reset
        return reset

    async def fail_pending(self, message: str) -> int:
        """Mark every pending document failed; return how many changed."""
        pending = [d for d in self.items.values() if d.status == "pending"]
        for document in pending:
            self.items[document.id] = replace(
                document, status="failed", error=message
            )
        return len(pending)


class SignallingDocumentRepository(InMemoryDocumentRepository):
    """Sets ``ready`` once any document is marked ready."""

    def __init__(self) -> None:
        """Initialize storage and the readiness signal."""
        super().__init__()
        self.ready = asyncio.Event()

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        """Update the status, then signal when a document became ready."""
        await super().set_status(document_id, status, error)
        if status == "ready":
            self.ready.set()


@dataclass
class _StoredChunk:
    chunk: Chunk
    embedding: list[float]


class InMemoryChunkRepository:
    """Simple chunk repository for tests.

    ``documents`` is set by ``in_memory_repositories``: search then returns
    only chunks of ``ready`` documents, as the join does in Postgres. Left
    unset, every stored chunk is searchable.
    """

    def __init__(self) -> None:
        """Initialize in-memory chunk storage."""
        self.items: list[_StoredChunk] = []
        self.documents: InMemoryDocumentRepository | None = None

    def remove_document(self, document_id: str) -> None:
        """Drop the chunks of a document (what its deletion cascades to)."""
        self.items = [
            item
            for item in self.items
            if item.chunk.document_id != document_id
        ]

    def _searchable(self, item: _StoredChunk) -> bool:
        if self.documents is None:
            return True
        document = self.documents.items.get(item.chunk.document_id)
        return document is not None and document.status == "ready"

    async def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Replace the document's stored chunks with these."""
        self.items = [
            item
            for item in self.items
            if item.chunk.document_id != document_id
        ]
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self.items.append(_StoredChunk(chunk=chunk, embedding=embedding))

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Return top-k chunks sorted by cosine similarity."""
        ranked = sorted(
            (item for item in self.items if self._searchable(item)),
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


def in_memory_repositories() -> tuple[
    InMemoryDocumentRepository, InMemoryChunkRepository
]:
    """A document and a chunk repository that behave like the Postgres pair.

    Deleting a document removes its chunks, and only chunks of ``ready``
    documents are searchable (the rule is in ``search_by_embedding``'s query
    there). Constructing the two repositories separately keeps them
    independent, which unit tests of a single use case rely on.
    """
    documents = InMemoryDocumentRepository()
    chunks = InMemoryChunkRepository()
    documents.chunks = chunks
    chunks.documents = documents
    return documents, chunks
