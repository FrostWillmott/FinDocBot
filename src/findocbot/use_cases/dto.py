"""Use-case data transfer objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResultDTO:
    """Single retrieval result."""

    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    score: float
    section: str | None = None


@dataclass(frozen=True)
class AskResponseDTO:
    """Answer plus retrieved context details."""

    answer: str
    sources: list[SearchResultDTO]
