"""Domain entities and value objects."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class Document:
    """Uploaded document metadata."""

    id: str
    filename: str
    # SHA-256 of the uploaded bytes; None for documents stored before it.
    content_hash: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )

    @staticmethod
    def create(filename: str, content_hash: str | None = None) -> Document:
        """Create a document with generated identifier."""
        return Document(
            id=str(uuid4()), filename=filename, content_hash=content_hash
        )


@dataclass(frozen=True)
class Chunk:
    """Document chunk prepared for retrieval."""

    id: str
    document_id: str
    chunk_index: int
    text: str
    section: str | None = None

    @staticmethod
    def create(
        document_id: str,
        chunk_index: int,
        text: str,
        section: str | None = None,
    ) -> Chunk:
        """Create chunk with generated identifier."""
        return Chunk(
            id=str(uuid4()),
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            section=section,
        )


@dataclass(frozen=True)
class ChatSession:
    """Dialog session; its id is the only credential for its history."""

    id: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )

    @staticmethod
    def create() -> ChatSession:
        """Create a session with an unguessable 256-bit identifier."""
        return ChatSession(id=secrets.token_urlsafe(32))


@dataclass(frozen=True)
class ChatTurn:
    """Q/A pair within a dialog session."""

    id: str
    session_id: str
    question: str
    answer: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )

    @staticmethod
    def create(session_id: str, question: str, answer: str) -> ChatTurn:
        """Create chat turn with generated identifier."""
        return ChatTurn(
            id=str(uuid4()),
            session_id=session_id,
            question=question,
            answer=answer,
        )
