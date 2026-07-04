"""Domain and use-case exceptions."""


class FinDocBotError(Exception):
    """Base project exception."""


class EmptyDocumentError(FinDocBotError):
    """Raised when extracted document content is empty."""


class InvalidQueryError(FinDocBotError):
    """Raised when a search or question is invalid."""


# --- Infrastructure / adapter exceptions ---


class InfrastructureError(FinDocBotError):
    """Base for errors originating in external systems (DB, model provider)."""


class ModelProviderError(InfrastructureError):
    """Raised when the model provider (Ollama) is unreachable or fails."""


class StorageError(InfrastructureError):
    """Raised when a persistence operation fails."""
