"""Factories shared across test modules."""

from __future__ import annotations

from fpdf import FPDF


def build_pdf_bytes(text: str) -> bytes:
    """Single-page PDF with *text* in 12 pt Helvetica."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    return bytes(pdf.output())
