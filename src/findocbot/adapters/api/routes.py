"""FastAPI routes adapter."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse

from findocbot.adapters.api.schemas import (
    AskRequest,
    AskResponse,
    ChunkResponse,
    DocumentResponse,
    SearchRequest,
    UploadResponse,
)
from findocbot.domain.entities import Document
from findocbot.domain.exceptions import (
    FinDocBotError,
    InfrastructureError,
    ModelProviderError,
    NotFoundError,
)
from findocbot.use_cases.answer_question import AnswerQuestionUseCase
from findocbot.use_cases.manage_documents import ManageDocumentsUseCase
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)
from findocbot.use_cases.upload_pdf import UploadPDFUseCase

logger = logging.getLogger(__name__)


class ApiServices(Protocol):
    """What the routes need; the app's container provides it."""

    upload_pdf: UploadPDFUseCase
    search_chunks: SearchSimilarChunksUseCase
    answer_question: AnswerQuestionUseCase
    manage_documents: ManageDocumentsUseCase
    # Each raises InfrastructureError when its system is down.
    health_checks: dict[str, Callable[[], Awaitable[None]]]


PDF_UPLOAD_FILE = File(...)
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_UPLOAD_MB = _MAX_UPLOAD_BYTES // 1024 // 1024


@contextmanager
def _map_use_case_errors() -> Generator[None, None, None]:
    """Map domain and infrastructure exceptions to HTTP status codes."""
    try:
        yield
    except ModelProviderError as error:
        # The message can name the provider's internal URL; log it, but
        # keep it out of the response.
        logger.error(f"Model provider error: {error}")
        raise HTTPException(
            status_code=502, detail="Model provider request failed."
        ) from error
    except InfrastructureError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FinDocBotError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def _run_health_check(
    name: str, check: Callable[[], Awaitable[None]]
) -> str:
    try:
        await check()
    except InfrastructureError as error:
        logger.warning(f"Health check {name} failed: {error}")
        return "unavailable"
    return "ok"


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        error=document.error,
        created_at=document.created_at,
    )


def _add_document_routes(router: APIRouter, container: ApiServices) -> None:
    @router.get("/documents", response_model=list[DocumentResponse])
    async def list_documents(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[DocumentResponse]:
        with _map_use_case_errors():
            documents = await container.manage_documents.list_documents(
                limit=limit, offset=offset
            )
        return [_document_response(document) for document in documents]

    # UUID path params: a malformed id is a 422 here, not a DB type error.
    @router.get("/documents/{document_id}", response_model=DocumentResponse)
    async def get_document(document_id: UUID) -> DocumentResponse:
        with _map_use_case_errors():
            document = await container.manage_documents.get_document(
                str(document_id)
            )
        return _document_response(document)

    @router.delete("/documents/{document_id}", status_code=204)
    async def delete_document(document_id: UUID) -> None:
        with _map_use_case_errors():
            await container.manage_documents.delete_document(str(document_id))


def build_router(container: ApiServices) -> APIRouter:
    """Build API router with use-case handlers."""
    router = APIRouter()

    @router.get("/health")
    async def healthcheck() -> JSONResponse:
        names = list(container.health_checks)
        results = await asyncio.gather(
            *(
                _run_health_check(name, container.health_checks[name])
                for name in names
            )
        )
        checks = dict(zip(names, results, strict=True))
        healthy = all(result == "ok" for result in results)
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "degraded",
                "checks": checks,
            },
        )

    @router.post("/documents/upload", response_model=UploadResponse)
    async def upload_document(
        response: Response,
        file: UploadFile = PDF_UPLOAD_FILE,
    ) -> UploadResponse:
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400, detail="Only PDF uploads are supported."
            )
        # Read in bounded chunks and abort early so an oversized upload
        # cannot be fully buffered in memory before the limit is enforced.
        content = bytearray()
        while data := await file.read(1024 * 1024):
            content.extend(data)
            if len(content) > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {_MAX_UPLOAD_MB} MB limit.",
                )
        with _map_use_case_errors():
            document = await container.upload_pdf.submit(
                filename=file.filename or "uploaded.pdf",
                content=bytes(content),
            )
        # A fresh upload is accepted for background ingestion; a re-upload of
        # the same bytes resolves to the already-stored document (200).
        response.status_code = 202 if document.status == "pending" else 200
        return UploadResponse(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
        )

    @router.post("/search", response_model=list[ChunkResponse])
    async def search_chunks(payload: SearchRequest) -> list[ChunkResponse]:
        with _map_use_case_errors():
            result = await container.search_chunks.execute(
                query=payload.query,
                top_k=payload.top_k,
            )
        return [
            ChunkResponse(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                chunk_index=item.chunk_index,
                text=item.text,
                score=item.score,
                section=item.section,
            )
            for item in result
        ]

    @router.post("/ask", response_model=AskResponse)
    async def ask_question(payload: AskRequest) -> AskResponse:
        with _map_use_case_errors():
            result = await container.answer_question.execute(
                session_id=payload.session_id,
                question=payload.question,
                top_k=payload.top_k,
            )
        return AskResponse(
            answer=result.answer,
            confidence=result.confidence,
            sources=[
                ChunkResponse(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    chunk_index=item.chunk_index,
                    text=item.text,
                    score=item.score,
                    section=item.section,
                )
                for item in result.sources
            ],
            session_id=result.session_id,
        )

    _add_document_routes(router, container)
    return router
