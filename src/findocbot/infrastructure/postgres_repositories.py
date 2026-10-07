"""PostgreSQL repository implementations."""

from __future__ import annotations

import asyncpg

from findocbot.domain.entities import (
    ChatSession,
    ChatTurn,
    Chunk,
    Document,
    DocumentStatus,
)
from findocbot.domain.exceptions import (
    DuplicateDocumentError,
    EmbeddingDimensionError,
    StorageError,
)
from findocbot.infrastructure.db import PostgresPool
from findocbot.use_cases.ports import ChunkWithScore


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9f}" for value in values) + "]"


def _document_from_row(row: asyncpg.Record) -> Document:
    return Document(
        id=str(row["id"]),
        filename=row["filename"],
        content_hash=row["content_hash"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
    )


class PostgresDocumentRepository:
    """Persist document metadata in PostgreSQL."""

    def __init__(self, db: PostgresPool) -> None:
        """Store db dependency."""
        self._db = db

    async def create(self, document: Document) -> None:
        """Insert document row."""
        try:
            await self._db.pool.execute(
                """
                INSERT INTO documents (
                    id, filename, content_hash, status, error, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                document.id,
                document.filename,
                document.content_hash,
                document.status,
                document.error,
                document.created_at,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateDocumentError("Document already exists") from exc
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to persist document") from exc

    async def find_by_content_hash(self, content_hash: str) -> Document | None:
        """Return the document stored with this content hash, if any."""
        try:
            row = await self._db.pool.fetchrow(
                """
                SELECT id, filename, content_hash, status, error, created_at
                FROM documents
                WHERE content_hash = $1
                """,
                content_hash,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to look up document") from exc
        return None if row is None else _document_from_row(row)

    async def get(self, document_id: str) -> Document | None:
        """Return the document with this id, if any."""
        try:
            row = await self._db.pool.fetchrow(
                """
                SELECT id, filename, content_hash, status, error, created_at
                FROM documents
                WHERE id = $1
                """,
                document_id,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to load document") from exc
        return None if row is None else _document_from_row(row)

    async def list_page(self, limit: int, offset: int) -> list[Document]:
        """Return documents, newest first."""
        try:
            rows = await self._db.pool.fetch(
                """
                SELECT id, filename, content_hash, status, error, created_at
                FROM documents
                ORDER BY created_at DESC, id
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to list documents") from exc
        return [_document_from_row(row) for row in rows]

    async def delete(self, document_id: str) -> bool:
        """Delete document row (chunks cascade); return whether it existed."""
        try:
            deleted_id = await self._db.pool.fetchval(
                "DELETE FROM documents WHERE id = $1 RETURNING id",
                document_id,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to delete document") from exc
        return deleted_id is not None

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: str | None = None,
    ) -> None:
        """Update a document's ingestion status and optional error message."""
        try:
            await self._db.pool.execute(
                """
                UPDATE documents
                SET status = $1, error = $2
                WHERE id = $3
                """,
                status,
                error,
                document_id,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to update document status") from exc


class PostgresChunkRepository:
    """Persist and search chunks with pgvector."""

    def __init__(self, db: PostgresPool, embedding_dim: int) -> None:
        """Store db dependency and the configured vector size."""
        self._db = db
        self._embedding_dim = embedding_dim

    async def verify_schema(self) -> None:
        """Fail fast if chunks.embedding differs from the configured size."""
        try:
            column_dim = await self._db.pool.fetchval(
                """
                SELECT atttypmod
                FROM pg_attribute
                WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'
                """
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to inspect chunks schema") from exc
        if column_dim != self._embedding_dim:
            raise EmbeddingDimensionError(
                f"chunks.embedding is vector({column_dim}) but EMBEDDING_DIM "
                f"is {self._embedding_dim}; re-run migrations or fix the "
                "setting."
            )

    def _check_dim(self, embedding: list[float]) -> None:
        # pgvector would reject the row too, but with an opaque error;
        # this names the setting to fix.
        if len(embedding) != self._embedding_dim:
            raise EmbeddingDimensionError(
                f"Embedding has {len(embedding)} dimensions, EMBEDDING_DIM is "
                f"{self._embedding_dim}; check OLLAMA_EMBED_MODEL."
            )

    async def add_chunks_with_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Insert chunks and matching vectors in a single batch."""
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings count mismatch.")

        if not chunks:
            return
        for embedding in embeddings:
            self._check_dim(embedding)

        try:
            async with self._db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(
                        """
                        INSERT INTO chunks (
                            id,
                            document_id,
                            chunk_index,
                            section,
                            content,
                            embedding
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::vector)
                        """,
                        [
                            (
                                c.id,
                                c.document_id,
                                c.chunk_index,
                                c.section,
                                c.text,
                                _vector_literal(e),
                            )
                            for c, e in zip(chunks, embeddings, strict=True)
                        ],
                    )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to persist chunks") from exc

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Search by cosine distance and map rows to DTO."""
        self._check_dim(embedding)
        try:
            rows = await self._db.pool.fetch(
                """
                SELECT
                    id,
                    document_id,
                    chunk_index,
                    section,
                    content,
                    1 - (embedding <=> $1::vector) AS score
                FROM chunks
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                _vector_literal(embedding),
                top_k,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to search chunks") from exc
        return [
            ChunkWithScore(
                chunk=Chunk(
                    id=str(row["id"]),
                    document_id=str(row["document_id"]),
                    chunk_index=row["chunk_index"],
                    section=row["section"],
                    text=row["content"],
                ),
                score=float(row["score"]),
            )
            for row in rows
        ]


class PostgresChatHistoryRepository:
    """Persist and load short chat history for prompt building."""

    def __init__(self, db: PostgresPool) -> None:
        """Store db dependency."""
        self._db = db

    async def create_session(self, session: ChatSession) -> None:
        """Insert an issued session."""
        try:
            await self._db.pool.execute(
                "INSERT INTO sessions (id, created_at) VALUES ($1, $2)",
                session.id,
                session.created_at,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to persist session") from exc

    async def session_exists(self, session_id: str) -> bool:
        """Return whether the session was issued."""
        try:
            found = await self._db.pool.fetchval(
                "SELECT EXISTS (SELECT 1 FROM sessions WHERE id = $1)",
                session_id,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to look up session") from exc
        return bool(found)

    async def add_turn(self, turn: ChatTurn) -> None:
        """Insert chat turn."""
        try:
            await self._db.pool.execute(
                """
                INSERT INTO chat_turns (
                    id,
                    session_id,
                    question,
                    answer,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                turn.id,
                turn.session_id,
                turn.question,
                turn.answer,
                turn.created_at,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to persist chat turn") from exc

    async def list_recent(self, session_id: str, limit: int) -> list[ChatTurn]:
        """Return newest history converted to chronological order."""
        try:
            rows = await self._db.pool.fetch(
                """
                SELECT id, session_id, question, answer, created_at
                FROM chat_turns
                WHERE session_id = $1
                ORDER BY created_at DESC, id DESC
                LIMIT $2
                """,
                session_id,
                limit,
            )
        except asyncpg.PostgresError as exc:
            raise StorageError("Failed to load chat history") from exc
        items = [
            ChatTurn(
                id=str(row["id"]),
                session_id=row["session_id"],
                question=row["question"],
                answer=row["answer"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return list(reversed(items))
