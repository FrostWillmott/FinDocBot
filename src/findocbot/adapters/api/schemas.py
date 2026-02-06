"""API request and response schemas."""

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request payload."""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class AskRequest(BaseModel):
    """Question request payload."""

    session_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class ChunkResponse(BaseModel):
    """Chunk response payload."""

    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    score: float
    section: str | None = None


class UploadResponse(BaseModel):
    """Upload operation response."""

    document_id: str
    filename: str


class AskResponse(BaseModel):
    """Answer response payload."""

    answer: str
    sources: list[ChunkResponse]
