"""Domain and use-case exceptions."""

from __future__ import annotations


class FinDocBotError(Exception):
    """Base project exception."""


class EmptyDocumentError(FinDocBotError):
    """Raised when extracted document content is empty."""


class InvalidDocumentError(FinDocBotError):
    """Raised when uploaded bytes cannot be read as a PDF."""


class InvalidQueryError(FinDocBotError):
    """Raised when a search or question is invalid."""


# --- Infrastructure / adapter exceptions ---


class InfrastructureError(FinDocBotError):
    """Base for errors originating in external systems (DB, model provider)."""


class ModelProviderError(InfrastructureError):
    """Raised when the model provider (Ollama) is unreachable or fails."""


class StorageError(InfrastructureError):
    """Raised when a persistence operation fails."""


class EmbeddingDimensionError(InfrastructureError):
    """Raised when embedding sizes disagree with the configured dimension."""
