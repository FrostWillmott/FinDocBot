"""Factories shared across test modules."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

# fpdf stamps the current second into the file. Two builds of the same text
# then differ whenever a second boundary falls between them, and the upload
# deduplication tests, which compare the bytes of two builds, flake.
_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def build_pdf_bytes(text: str) -> bytes:
    """Single-page PDF with *text* in 12 pt Helvetica."""
    pdf = FPDF()
    pdf.set_creation_date(_CREATED)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    return bytes(pdf.output())


def build_encrypted_pdf_bytes(
    text: str,
    *,
    algorithm: str = "AES-128",
    user_password: str = "",
    owner_password: str = "owner",
) -> bytes:
    """The `build_pdf_bytes` PDF encrypted with *algorithm*.

    AES draws a random IV and file id per build, so two builds of the same
    text differ: keep these out of the deduplication tests.
    """
    writer = PdfWriter(clone_from=PdfReader(BytesIO(build_pdf_bytes(text))))
    writer.encrypt(
        user_password=user_password,
        owner_password=owner_password,
        algorithm=algorithm,
    )
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
