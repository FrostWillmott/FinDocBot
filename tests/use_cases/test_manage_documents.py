from __future__ import annotations

from datetime import UTC, datetime

import pytest

from findocbot.domain.entities import Document
from findocbot.domain.exceptions import DocumentNotFoundError
from findocbot.infrastructure.in_memory import InMemoryDocumentRepository
from findocbot.use_cases.manage_documents import ManageDocumentsUseCase


def _document(name: str, day: int) -> Document:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return Document(id=name, filename=f"{name}.pdf", created_at=created_at)


@pytest.fixture
def documents() -> InMemoryDocumentRepository:
    repo = InMemoryDocumentRepository()
    for name, day in [("old", 1), ("mid", 2), ("new", 3)]:
        repo.items[name] = _document(name, day)
    return repo


async def test_list_documents_page_returns_newest_first_from_offset(
    documents: InMemoryDocumentRepository,
) -> None:
    manage = ManageDocumentsUseCase(documents)

    page = await manage.list_documents(limit=2, offset=1)

    assert [doc.id for doc in page] == ["mid", "old"]


async def test_get_document_unknown_id_raises_not_found(
    documents: InMemoryDocumentRepository,
) -> None:
    with pytest.raises(DocumentNotFoundError):
        await ManageDocumentsUseCase(documents).get_document("missing")


async def test_delete_document_existing_id_removes_it(
    documents: InMemoryDocumentRepository,
) -> None:
    await ManageDocumentsUseCase(documents).delete_document("mid")

    assert sorted(documents.items) == ["new", "old"]


async def test_delete_document_unknown_id_raises_not_found(
    documents: InMemoryDocumentRepository,
) -> None:
    with pytest.raises(DocumentNotFoundError):
        await ManageDocumentsUseCase(documents).delete_document("missing")
