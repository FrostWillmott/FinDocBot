"""List, inspect and delete stored documents."""

from __future__ import annotations

from findocbot.domain.entities import Document
from findocbot.domain.exceptions import DocumentNotFoundError
from findocbot.use_cases.ports import DocumentRepositoryPort


class ManageDocumentsUseCase:
    """Read and remove indexed documents."""

    def __init__(self, documents: DocumentRepositoryPort) -> None:
        """Store the document repository."""
        self._documents = documents

    async def list_documents(self, limit: int, offset: int) -> list[Document]:
        """Return a page of documents, newest first."""
        return await self._documents.list_page(limit=limit, offset=offset)

    async def get_document(self, document_id: str) -> Document:
        """Return one document or raise DocumentNotFoundError."""
        document = await self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")
        return document

    async def delete_document(self, document_id: str) -> None:
        """Delete a document with its chunks, so search stops returning it."""
        if not await self._documents.delete(document_id):
            raise DocumentNotFoundError("Document not found.")
