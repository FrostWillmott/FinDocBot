"""Factories shared across test modules."""

from __future__ import annotations

from datetime import UTC, datetime

from fpdf import FPDF

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
