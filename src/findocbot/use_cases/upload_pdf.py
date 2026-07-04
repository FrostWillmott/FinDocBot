"""Upload PDF use case."""

import asyncio

from findocbot.domain.entities import Chunk, Document
from findocbot.domain.exceptions import EmptyDocumentError
from findocbot.use_cases.ports import (
    ChunkerPort,
    ChunkRepositoryPort,
    DocumentRepositoryPort,
    ModelProviderGateway,
    PDFParserPort,
)


class UploadPDFUseCase:
    """Extract, chunk, embed, and save uploaded PDF."""

    def __init__(
        self,
        parser: PDFParserPort,
        chunker: ChunkerPort,
        provider: ModelProviderGateway,
        documents: DocumentRepositoryPort,
        chunks: ChunkRepositoryPort,
    ) -> None:
        """Store dependencies for upload workflow."""
        self._parser = parser
        self._chunker = chunker
        self._provider = provider
        self._documents = documents
        self._chunks = chunks

    async def execute(self, filename: str, content: bytes) -> Document:
        """Run upload pipeline and return created document.

        CPU-bound PDF parsing and chunking are offloaded to a thread
        so they do not block the event loop.
        """
        text = (
            await asyncio.to_thread(self._parser.extract_text, content)
        ).strip()
        if not text:
            raise EmptyDocumentError("Uploaded PDF does not contain text.")

        document = Document.create(filename=filename)

        chunk_parts = await asyncio.to_thread(self._chunker.split, text)
        built_chunks = [
            Chunk.create(
                document_id=document.id,
                chunk_index=index,
                text=chunk_text,
                section=section,
            )
            for index, (chunk_text, section) in enumerate(chunk_parts)
            if chunk_text.strip()
        ]

        embeddings = await self._provider.embed_many([
            c.text for c in built_chunks
        ])
        # Persist the document only after embedding succeeds so that
        # a provider failure does not leave an orphan document row.
        await self._documents.create(document)
        await self._chunks.add_chunks_with_embeddings(built_chunks, embeddings)
        return document
