"""Domain and use-case exceptions."""


class FinDocBotError(Exception):
    """Base project exception."""


class EmptyDocumentError(FinDocBotError):
    """Raised when extracted document content is empty."""


class DocumentNotFoundError(FinDocBotError):
    """Raised when document is not found in persistence."""


class InvalidQueryError(FinDocBotError):
    """Raised when a search or question is invalid."""
