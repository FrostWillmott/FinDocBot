"""Behaviour every repository adapter must show.

The in-memory fakes (``tests/unit``) and Postgres (``tests/integration``) run
the same cases, so a fake cannot drift from the database unnoticed. The
classes here have no ``Test`` prefix on purpose: pytest collects only their
subclasses, which supply the ``repos`` fixture.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from findocbot.domain.entities import Chunk, Document, DocumentStatus
from findocbot.domain.exceptions import DuplicateDocumentError
from findocbot.use_cases.ports import (
    ChunkRepositoryPort,
    DocumentRepositoryPort,
)

# Well-formed (Postgres ids are UUIDs) and never issued.
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class Repositories:
    """Both repositories of one adapter, sharing one store."""

    documents: DocumentRepositoryPort
    chunks: ChunkRepositoryPort
    dim: int

    def vector(self, *lead: float) -> list[float]:
        """An embedding of the adapter's size starting with *lead*."""
        return [*lead, *([0.0] * (self.dim - len(lead)))]

    async def store_chunk(
        self, document: Document, text: str = "x", index: int = 0
    ) -> Chunk:
        """Store one chunk of *document*, found by ``vector(1)``."""
        chunk = Chunk.create(
            document_id=document.id, chunk_index=index, text=text
        )
        await self.chunks.replace_document_chunks(
            document.id, [chunk], [self.vector(1.0)]
        )
        return chunk

    async def search_ids(self, top_k: int = 5) -> list[str]:
        """Ids of the chunks a search for ``vector(1)`` returns."""
        found = await self.chunks.search_by_embedding(
            self.vector(1.0), top_k=top_k
        )
        return [result.chunk.id for result in found]


class DocumentRepositoryContract:
    """Cases for ``DocumentRepositoryPort``; subclasses provide ``repos``."""

    @pytest.fixture
    async def repos(self) -> Repositories:
        raise NotImplementedError

    async def test_get_after_create_returns_the_document(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(
            filename="a.pdf", content_hash="abc", status="ready"
        )
        await repos.documents.create(doc)

        assert await repos.documents.get(doc.id) == doc

    async def test_get_unknown_id_returns_none(
        self, repos: Repositories
    ) -> None:
        assert await repos.documents.get(UNKNOWN_ID) is None

    async def test_find_by_content_hash_after_create_returns_it(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(
            filename="a.pdf", content_hash="abc", status="ready"
        )
        await repos.documents.create(doc)

        assert await repos.documents.find_by_content_hash("abc") == doc

    async def test_create_same_content_hash_raises_duplicate(
        self, repos: Repositories
    ) -> None:
        await repos.documents.create(
            Document.create(
                filename="a.pdf", content_hash="abc", status="ready"
            )
        )
        duplicate = Document.create(
            filename="b.pdf", content_hash="abc", status="ready"
        )

        with pytest.raises(DuplicateDocumentError):
            await repos.documents.create(duplicate)

    async def test_create_two_without_hash_keeps_both(
        self, repos: Repositories
    ) -> None:
        await repos.documents.create(
            Document.create(filename="a.pdf", status="ready")
        )
        await repos.documents.create(
            Document.create(filename="b.pdf", status="ready")
        )

        assert len(await repos.documents.list_page(limit=10, offset=0)) == 2

    async def test_list_page_returns_newest_first(
        self, repos: Repositories
    ) -> None:
        older = Document.create(filename="older.pdf", status="ready")
        newer = Document.create(filename="newer.pdf", status="ready")
        await repos.documents.create(older)
        await repos.documents.create(newer)

        page = await repos.documents.list_page(limit=1, offset=0)

        assert [doc.id for doc in page] == [newer.id]

    async def test_delete_twice_reports_whether_it_existed(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="ready")
        await repos.documents.create(doc)

        assert (
            await repos.documents.delete(doc.id),
            await repos.documents.delete(doc.id),
        ) == (True, False)

    async def test_delete_removes_its_chunks_from_search(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="ready")
        await repos.documents.create(doc)
        await repos.store_chunk(doc)

        await repos.documents.delete(doc.id)

        assert await repos.search_ids() == []

    async def test_set_status_stores_the_status_and_error(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="pending")
        await repos.documents.create(doc)

        await repos.documents.set_status(doc.id, "failed", "boom")

        stored = await repos.documents.get(doc.id)
        assert stored is not None
        assert (stored.status, stored.error) == ("failed", "boom")

    async def test_set_status_unknown_id_changes_nothing(
        self, repos: Repositories
    ) -> None:
        # The worker finishing a job for a document deleted meanwhile.
        await repos.documents.set_status(UNKNOWN_ID, "ready")

        assert await repos.documents.list_page(limit=10, offset=0) == []

    async def test_reset_failed_claims_a_failed_document_once(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="pending")
        await repos.documents.create(doc)
        await repos.documents.set_status(doc.id, "failed", "boom")

        first = await repos.documents.reset_failed(doc.id)
        second = await repos.documents.reset_failed(doc.id)

        assert first is not None
        assert (first.status, first.error, second) == ("pending", None, None)

    @pytest.mark.parametrize("status", ["pending", "ready"])
    async def test_reset_failed_non_failed_document_returns_none(
        self, repos: Repositories, status: DocumentStatus
    ) -> None:
        doc = Document.create(filename="a.pdf", status=status)
        await repos.documents.create(doc)

        assert await repos.documents.reset_failed(doc.id) is None

    async def test_fail_pending_marks_only_pending_documents_failed(
        self, repos: Repositories
    ) -> None:
        pending = Document.create(filename="p.pdf", status="pending")
        ready = Document.create(filename="r.pdf", status="ready")
        for doc in (pending, ready):
            await repos.documents.create(doc)

        count = await repos.documents.fail_pending("interrupted")

        statuses = {
            doc.id: (stored.status, stored.error)
            for doc in (pending, ready)
            if (stored := await repos.documents.get(doc.id)) is not None
        }
        assert (count, statuses) == (
            1,
            {
                pending.id: ("failed", "interrupted"),
                ready.id: ("ready", None),
            },
        )

    async def test_fail_pending_without_pending_documents_returns_zero(
        self, repos: Repositories
    ) -> None:
        await repos.documents.create(
            Document.create(filename="r.pdf", status="ready")
        )

        assert await repos.documents.fail_pending("interrupted") == 0


class ChunkRepositoryContract:
    """Cases for ``ChunkRepositoryPort``; subclasses provide ``repos``."""

    @pytest.fixture
    async def repos(self) -> Repositories:
        raise NotImplementedError

    async def test_search_empty_store_returns_nothing(
        self, repos: Repositories
    ) -> None:
        assert await repos.search_ids() == []

    async def test_search_after_replace_returns_closest_first(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="report.pdf", status="ready")
        await repos.documents.create(doc)
        chunks = [
            Chunk.create(document_id=doc.id, chunk_index=i, text=text)
            for i, text in enumerate(["Revenue grew by 20%", "Profit stable"])
        ]
        # Zero vectors have no cosine direction (and HNSW skips them), so
        # both are non-zero; the second points the way the query does.
        await repos.chunks.replace_document_chunks(
            doc.id, chunks, [repos.vector(0.0, 0.9), repos.vector(0.9)]
        )

        found = await repos.chunks.search_by_embedding(
            repos.vector(0.5), top_k=2
        )

        assert [result.chunk.id for result in found] == [
            chunks[1].id,
            chunks[0].id,
        ]

    async def test_search_returns_ids_as_strings(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="ready")
        await repos.documents.create(doc)
        await repos.store_chunk(doc)

        (result,) = await repos.chunks.search_by_embedding(
            repos.vector(1.0), top_k=1
        )

        assert (type(result.chunk.id), type(result.chunk.document_id)) == (
            str,
            str,
        )

    @pytest.mark.parametrize("status", ["pending", "failed"])
    async def test_search_non_ready_document_returns_nothing(
        self, repos: Repositories, status: DocumentStatus
    ) -> None:
        doc = Document.create(filename="a.pdf", status=status)
        await repos.documents.create(doc)
        await repos.store_chunk(doc)

        assert await repos.search_ids() == []

    async def test_search_after_document_marked_ready_returns_its_chunk(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="pending")
        await repos.documents.create(doc)
        chunk = await repos.store_chunk(doc)

        await repos.documents.set_status(doc.id, "ready")

        assert await repos.search_ids() == [chunk.id]

    async def test_replace_leaves_exactly_the_new_set(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="ready")
        await repos.documents.create(doc)
        old = [
            Chunk.create(document_id=doc.id, chunk_index=i, text=f"old {i}")
            for i in range(2)
        ]
        await repos.chunks.replace_document_chunks(
            doc.id, old, [repos.vector(1.0), repos.vector(1.0)]
        )
        new = Chunk.create(document_id=doc.id, chunk_index=0, text="new")

        await repos.chunks.replace_document_chunks(
            doc.id, [new], [repos.vector(1.0)]
        )

        assert await repos.search_ids() == [new.id]

    async def test_replace_with_nothing_clears_the_previous_chunks(
        self, repos: Repositories
    ) -> None:
        doc = Document.create(filename="a.pdf", status="ready")
        await repos.documents.create(doc)
        await repos.store_chunk(doc)

        await repos.chunks.replace_document_chunks(doc.id, [], [])

        assert await repos.search_ids() == []
