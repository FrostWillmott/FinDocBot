from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

import pytest
from fpdf import FPDF
from pypdf.errors import DependencyError

from findocbot.domain.exceptions import (
    InfrastructureError,
    InvalidDocumentError,
)
from findocbot.infrastructure import pdf_parser
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import (
    PyPDFParser,
    TextLine,
    join_lines,
)
from tests.factories import build_encrypted_pdf_bytes, build_pdf_bytes


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


# Same-length edits keep the xref offsets valid, so pypdf gets past parsing
# and fails inside its internals with a builtin, not a PyPdfError. pypdf 6.20
# stopped raising on a bad /Subtype (the old KeyError reproduction);
# /FlateDecode still leaks a raw NotImplementedError.
@pytest.mark.parametrize(
    ("original", "broken"),
    [
        (b"/FlateDecode", b"/FlateDecodX"),  # NotImplementedError
    ],
)
def test_extract_text_pypdf_internal_error_raises_invalid_document(
    original: bytes, broken: bytes
) -> None:
    content = build_pdf_bytes("Revenue grew.").replace(original, broken)

    with pytest.raises(InvalidDocumentError, match="not a readable PDF"):
        PyPDFParser().extract_text(content)


# An empty user password opens the file without one; pypdf tries it itself.
def test_extract_text_aes128_encrypted_empty_user_password_returns_text() -> (
    None
):
    content = build_encrypted_pdf_bytes("Revenue grew.", algorithm="AES-128")

    assert PyPDFParser().extract_text(content) == "Revenue grew."


def test_extract_text_aes256_encrypted_empty_user_password_returns_text() -> (
    None
):
    content = build_encrypted_pdf_bytes("Revenue grew.", algorithm="AES-256")

    assert PyPDFParser().extract_text(content) == "Revenue grew."


def test_extract_text_rc4_encrypted_empty_user_password_returns_text() -> None:
    content = build_encrypted_pdf_bytes("Revenue grew.", algorithm="RC4-128")

    assert PyPDFParser().extract_text(content) == "Revenue grew."


def test_extract_text_password_protected_pdf_raises_invalid_document() -> None:
    content = build_encrypted_pdf_bytes(
        "Revenue grew.", algorithm="RC4-128", user_password="secret"
    )

    with pytest.raises(
        InvalidDocumentError,
        match="not a readable PDF: File has not been decrypted",
    ):
        PyPDFParser().extract_text(content)


def test_extract_text_missing_crypto_provider_raises_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pypdf raises this for an AES file when no crypto provider is installed.
    def reader_without_crypto(stream: object) -> NoReturn:
        raise DependencyError("crypto provider missing")

    monkeypatch.setattr(pdf_parser, "PdfReader", reader_without_crypto)

    with pytest.raises(InfrastructureError, match="cannot decrypt"):
        PyPDFParser().extract_text(build_pdf_bytes("Revenue grew."))


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


def test_extract_text_two_column_table_rows_keep_row_order() -> None:
    # Same geometry as prose columns written row by row, which still
    # interleave (see docs/column-reading-order.md); a fix must keep this.
    rows = [
        ("Revenue", "1,284"),
        ("Operating costs", "912"),
        ("Net profit", "372"),
        ("Dividend", "120"),
    ]

    def draw(pdf: FPDF) -> None:
        top = pdf.get_y()
        for i, (label, value) in enumerate(rows):
            pdf.set_xy(10, top + 5 * i)
            pdf.cell(90, 5, label)
            pdf.set_xy(110, top + 5 * i)
            pdf.cell(90, 5, value)

    extracted = PyPDFParser().extract_text(_pdf_bytes(draw))

    expected = [f"{label} {value}" for label, value in rows]
    assert extracted.split("\n") == expected


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


# 10 pt body at a 14.2 pt pitch (spacing 1.42), as fpdf's multi_cell(0, 5).
@pytest.mark.parametrize("heading_size", [14.0, 16.0, 20.0])
def test_join_lines_large_heading_after_body_with_close_gap_breaks_paragraph(
    heading_size: float,
) -> None:
    # The 24 pt gap is ~1.7x the body pitch but under 1.8 heading sizes.
    lines = [
        _line("a1", 800),
        _line("a2", 785.8),
        TextLine("Section 2", 761.8, heading_size),
        _line("b1", 731.8),
        _line("b2", 717.6),
    ]

    assert join_lines(lines) == "a1\na2\n\nSection 2\n\nb1\nb2"


def test_join_lines_large_first_word_mid_paragraph_keeps_lines() -> None:
    lines = [
        _line("a1", 800),
        TextLine("A2 starts with a large initial", 785.8, 20.0),
        _line("a3", 771.6),
        _line("a4", 757.4),
    ]

    assert join_lines(lines) == "a1\nA2 starts with a large initial\na3\na4"


def test_join_lines_small_first_piece_mid_paragraph_keeps_lines() -> None:
    lines = [
        _line("a1", 800),
        TextLine("1 footnote marker begins it", 785.8, 7.0),
        _line("a3", 771.6),
        _line("a4", 757.4),
    ]

    assert join_lines(lines) == "a1\n1 footnote marker begins it\na3\na4"


def test_join_lines_large_heading_above_body_breaks_paragraph() -> None:
    lines = [
        TextLine("Section 1", 800, 20.0),
        _line("b1", 770),
        _line("b2", 755.8),
    ]

    assert join_lines(lines) == "Section 1\n\nb1\nb2"


def _footnotes(top: float, count: int) -> list[TextLine]:
    # 7 pt footnotes at a 9.8 pt pitch (spacing 1.4 in their own size).
    return [TextLine(f"f{i + 1}", top - 9.8 * i, 7.0) for i in range(count)]


def test_join_lines_body_lines_on_footnote_heavy_page_stay_together() -> None:
    # Five 7 pt lines make 7 the page median; body pitch 14.2 is 2.03 of it.
    lines = [
        _line("b1", 800),
        _line("b2", 785.8),
        _line("b3", 771.6),
        *_footnotes(751.6, 5),
    ]

    assert join_lines(lines) == "b1\nb2\nb3\n\nf1\nf2\nf3\nf4\nf5"


def test_join_lines_footnote_blocks_under_larger_body_keep_breaks() -> None:
    # 10 pt body is the median; the 13.8 pt gaps between 7 pt footnotes are
    # 1.4x their 9.8 pt pitch, but only 1.38 of the median.
    body = [_line(f"b{i}", 800 - 14.2 * i) for i in range(12)]
    notes = [
        TextLine(text, top - 9.8 * row, 7.0)
        for top, names in [(623.8, "ab"), (600.2, "cd"), (576.6, "ef")]
        for row, text in enumerate(f"f{name}" for name in names)
    ]

    result = join_lines([*body, *notes])

    assert result.split("\n\n")[1:] == ["fa\nfb", "fc\nfd", "fe\nff"]


def test_join_lines_half_large_title_page_breaks_before_body() -> None:
    lines = [
        TextLine("t1", 800, 20.0),
        TextLine("t2", 776, 20.0),
        _line("b1", 740),
        _line("b2", 725.8),
    ]

    assert join_lines(lines) == "t1\nt2\n\nb1\nb2"


def test_extract_text_large_heading_after_body_keeps_section_label() -> None:
    body = "Revenue grew steadily across all regions this year. " * 3

    def draw(pdf: FPDF) -> None:
        _paragraph(pdf, body, gap_after=4)
        pdf.set_font("Helvetica", size=20)
        heading = "Section 2. Financial Highlights"
        pdf.multi_cell(0, 10, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", size=10)
        _paragraph(pdf, "Net profit was USD 132 million.", gap_after=4)

    text = PyPDFParser().extract_text(_pdf_bytes(draw))
    chunks = ParagraphTokenChunker(chunk_tokens=300).split(text)

    sections = [section for chunk, section in chunks if "Section 2" in chunk]
    assert sections == ["Section 2. Financial Highlights"]


def test_extract_text_small_marker_on_wrapped_line_keeps_paragraph() -> None:
    # A 7 pt footnote marker opens the second line; its gap is 13.3 pt.
    def draw(pdf: FPDF) -> None:
        pdf.cell(0, 5, "Revenue grew", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=7)
        width = pdf.get_string_width("1")
        pdf.cell(width, 5, "1", new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 5, " this year.", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, "Margins held.", new_x="LMARGIN", new_y="NEXT")

    extracted = PyPDFParser().extract_text(_pdf_bytes(draw))

    assert extracted == "Revenue grew\n1 this year.\nMargins held."
