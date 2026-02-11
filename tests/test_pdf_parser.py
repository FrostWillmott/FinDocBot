from fpdf import FPDF

from findocbot.infrastructure.pdf_parser import PyPDFParser


def _build_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    data = pdf.output()
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, bytes):
        return data
    return data.encode("latin-1")


def test_pdf_parser_extracts_text() -> None:
    parser = PyPDFParser()
    pdf_bytes = _build_pdf_bytes("Revenue increased by 12% in Q4.")

    extracted = parser.extract_text(pdf_bytes)

    assert "Revenue increased by 12% in Q4." in extracted
