"""PDF parsing implementation."""

from io import BytesIO

from pypdf import PdfReader


class PyPDFParser:
    """Extract text from PDF bytes with pypdf."""

    def extract_text(self, content: bytes) -> str:
        """Return concatenated page text."""
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(text.strip() for text in pages if text.strip())
