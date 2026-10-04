from __future__ import annotations

from collections.abc import Callable

import pytest
from fpdf import FPDF

from findocbot.domain.exceptions import InvalidDocumentError
from findocbot.infrastructure.pdf_parser import (
    PyPDFParser,
    TextLine,
    join_lines,
)
from tests.factories import build_pdf_bytes


def test_extract_text_single_line_pdf_returns_its_text() -> None:
    parser = PyPDFParser()
    pdf_bytes = build_pdf_bytes("Revenue increased by 12% in Q4.")

    extracted = parser.extract_text(pdf_bytes)

    assert "Revenue increased by 12% in Q4." in extracted


@pytest.mark.parametrize("content", [b"not a pdf", b""])
def test_extract_text_unreadable_bytes_raises_invalid_document(
    content: bytes,
) -> None:
    parser = PyPDFParser()

    with pytest.raises(InvalidDocumentError, match="not a readable PDF"):
        parser.extract_text(content)


def _pdf_bytes(draw: Callable[[FPDF], None]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    draw(pdf)
    return bytes(pdf.output())


def _paragraph(pdf: FPDF, text: str, gap_after: float) -> None:
    pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(gap_after)


def test_extract_text_vertical_gap_yields_paragraph_break() -> None:
    def draw(pdf: FPDF) -> None:
        _paragraph(pdf, "Section 2. Financial Highlights", gap_after=5)
        _paragraph(pdf, "Net profit was USD 132 million.", gap_after=5)

    extracted = PyPDFParser().extract_text(_pdf_bytes(draw))

    assert extracted == (
        "Section 2. Financial Highlights\n\nNet profit was USD 132 million."
    )


def test_extract_text_wrapped_lines_stay_in_one_paragraph() -> None:
    body = "Revenue grew steadily across all regions this year. " * 4

    def draw(pdf: FPDF) -> None:
        _paragraph(pdf, "Section 1. Results", gap_after=3)
        _paragraph(pdf, body, gap_after=3)
        _paragraph(pdf, "Section 2. Outlook", gap_after=3)

    extracted = PyPDFParser().extract_text(_pdf_bytes(draw))

    heading1, paragraph, heading2 = extracted.split("\n\n")
    assert "\n" in paragraph  # the body really wraps
    assert (heading1, paragraph.replace("\n", " "), heading2) == (
        "Section 1. Results",
        body.strip(),
        "Section 2. Outlook",
    )


def test_extract_text_two_columns_keep_reading_order() -> None:
    left = "Left column covers revenue growth in the logistics segment."
    right = "Right column covers the currency hedging policy in detail."

    def draw(pdf: FPDF) -> None:
        top = pdf.get_y()
        pdf.set_xy(10, top)
        pdf.multi_cell(90, 5, left)
        pdf.set_xy(110, top)
        pdf.multi_cell(90, 5, right)

    extracted = PyPDFParser().extract_text(_pdf_bytes(draw))

    left_text, right_text = extracted.split("\n\n")
    assert left_text.replace("\n", " ") == left
    assert right_text.replace("\n", " ") == right


def _line(text: str, y: float) -> TextLine:
    return TextLine(text=text, y=y, font_size=10.0)


def test_join_lines_gap_wider_than_line_pitch_breaks_paragraph() -> None:
    lines = [
        _line("a1", 800),
        _line("a2", 786),
        _line("a3", 772),
        _line("b1", 752),
        _line("b2", 738),
    ]

    assert join_lines(lines) == "a1\na2\na3\n\nb1\nb2"


def test_join_lines_dense_paragraphs_break_between_them() -> None:
    # Half the gaps are paragraph breaks; an average would hide them.
    lines = [
        _line("a1", 800),
        _line("a2", 786),
        _line("b1", 766),
        _line("b2", 752),
        _line("c1", 732),
    ]

    assert join_lines(lines) == "a1\na2\n\nb1\nb2\n\nc1"


def test_join_lines_jump_up_the_page_breaks_paragraph() -> None:
    lines = [_line("left end", 100), _line("right top", 800)]

    assert join_lines(lines) == "left end\n\nright top"


def test_join_lines_one_line_paragraphs_break_without_tight_pair() -> None:
    lines = [_line("Section 1", 800), _line("One line.", 778)]

    assert join_lines(lines) == "Section 1\n\nOne line."


def test_join_lines_zero_font_size_never_breaks() -> None:
    lines = [TextLine("a", 800, 0.0), TextLine("b", 700, 0.0)]

    assert join_lines(lines) == "a\nb"
