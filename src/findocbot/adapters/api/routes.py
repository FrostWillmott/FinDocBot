"""FastAPI routes adapter."""

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import APIRouter, File, HTTPException, UploadFile

from findocbot.adapters.api.schemas import (
    AskRequest,
    AskResponse,
    ChunkResponse,
    SearchRequest,
    UploadResponse,
)
from findocbot.domain.exceptions import (
    FinDocBotError,
    InfrastructureError,
    ModelProviderError,
)
from findocbot.infrastructure.container import AppContainer

PDF_UPLOAD_FILE = File(...)
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_UPLOAD_MB = _MAX_UPLOAD_BYTES // 1024 // 1024


@contextmanager
def _map_use_case_errors() -> Generator[None, None, None]:
    """Map domain and infrastructure exceptions to HTTP status codes."""
    try:
        yield
    except ModelProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except InfrastructureError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FinDocBotError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def build_router(container: AppContainer) -> APIRouter:
    """Build API router with use-case handlers."""
    router = APIRouter()

    @router.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/documents/upload", response_model=UploadResponse)
    async def upload_document(
        file: UploadFile = PDF_UPLOAD_FILE,
    ) -> UploadResponse:
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400, detail="Only PDF uploads are supported."
            )
        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {_MAX_UPLOAD_MB} MB limit.",
            )
        with _map_use_case_errors():
            document = await container.upload_pdf.execute(
                filename=file.filename or "uploaded.pdf",
                content=content,
            )
        return UploadResponse(
            document_id=document.id, filename=document.filename
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
        )

    return router
