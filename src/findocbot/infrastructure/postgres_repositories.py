"""PostgreSQL repository implementations."""

from findocbot.domain.entities import ChatTurn, Chunk, Document
from findocbot.infrastructure.db import PostgresPool
from findocbot.use_cases.ports import ChunkWithScore


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9f}" for value in values) + "]"


class PostgresDocumentRepository:
    """Persist document metadata in PostgreSQL."""

    def __init__(self, db: PostgresPool) -> None:
        """Store db dependency."""
        self._db = db

    async def create(self, document: Document) -> None:
        """Insert document row."""
        await self._db.pool.execute(
            """
            INSERT INTO documents (id, filename, created_at)
            VALUES ($1, $2, $3)
            """,
            document.id,
            document.filename,
            document.created_at,
        )


class PostgresChunkRepository:
    """Persist and search chunks with pgvector."""

    def __init__(self, db: PostgresPool) -> None:
        """Store db dependency."""
        self._db = db

    async def add_chunks_with_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Insert chunks and matching vectors."""
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings count mismatch.")

        async with self._db.pool.acquire() as conn:
            async with conn.transaction():
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    await conn.execute(
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
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.section,
                        chunk.text,
                        _vector_literal(embedding),
                    )

    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Search by cosine distance and map rows to DTO."""
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
        return [
            ChunkWithScore(
                chunk=Chunk(
                    id=row["id"],
                    document_id=row["document_id"],
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

    async def add_turn(self, turn: ChatTurn) -> None:
        """Insert chat turn."""
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

    async def list_recent(self, session_id: str, limit: int) -> list[ChatTurn]:
        """Return newest history converted to chronological order."""
        rows = await self._db.pool.fetch(
            """
            SELECT id, session_id, question, answer, created_at
            FROM chat_turns
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            session_id,
            limit,
        )
        items = [
            ChatTurn(
                id=row["id"],
                session_id=row["session_id"],
                question=row["question"],
                answer=row["answer"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return list(reversed(items))
