"""FastAPI routes adapter."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from findocbot.adapters.api.schemas import (
    AskRequest,
    AskResponse,
    ChunkResponse,
    SearchRequest,
    UploadResponse,
)
from findocbot.domain.exceptions import FinDocBotError
from findocbot.infrastructure.container import AppContainer

PDF_UPLOAD_FILE = File(...)
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_UPLOAD_MB = _MAX_UPLOAD_BYTES // 1024 // 1024


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
        try:
            document = await container.upload_pdf.execute(
                filename=file.filename or "uploaded.pdf",
                content=content,
            )
        except FinDocBotError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return UploadResponse(
            document_id=document.id, filename=document.filename
        )

    @router.post("/search", response_model=list[ChunkResponse])
    async def search_chunks(payload: SearchRequest) -> list[ChunkResponse]:
        try:
            result = await container.search_chunks.execute(
                query=payload.query,
                top_k=payload.top_k,
            )
        except FinDocBotError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
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
        try:
            result = await container.answer_question.execute(
                session_id=payload.session_id,
                question=payload.question,
                top_k=payload.top_k,
            )
        except FinDocBotError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
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
