"""PDF parsing implementation."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError

from findocbot.domain.exceptions import InvalidDocumentError

logger = logging.getLogger(__name__)

# Builtins pypdf raises from its internals on malformed files instead of a
# PyPdfError; each was seen fuzzing corrupted PDFs (see DECISIONS.md).
_PYPDF_INTERNAL_ERRORS = (
    KeyError,
    AttributeError,
    NotImplementedError,
    TypeError,
    ValueError,
    IndexError,
    UnboundLocalError,
)

# Spacing is the baseline gap between two lines in units of font size;
# single-spaced text sits at ~1.2-1.6. A paragraph break is spacing 1.3x
# the page's tightest line spacing...
_PARAGRAPH_GAP_FACTOR = 1.3
# ...capped at 1.8: a page of one-line paragraphs and headings has no
# single-spaced pair to measure against.
_MAX_LINE_SPACING = 1.8
# Closer than one font size is a super/subscript, not a separate line.
_MIN_LINE_SPACING = 1.0
# Text jumping up the page starts the next column or a new text block.
_JUMP_UP_SPACING = -0.5


@dataclass(frozen=True)
class TextLine:
    """One extracted line with its baseline height and font size (in pt)."""

    text: str
    y: float
    font_size: float


class PyPDFParser:
    """Extract text from PDF bytes with pypdf."""

    def extract_text(self, content: bytes) -> str:
        """Return page text with blank lines between paragraphs."""
        # pypdf parses lazily: a bad header fails in the constructor, an
        # encrypted file on `.pages`, a broken stream inside extraction.
        try:
            reader = PdfReader(BytesIO(content))
            pages = [_extract_page(page) for page in reader.pages]
        except PyPdfError as exc:
            raise InvalidDocumentError(
                f"Uploaded file is not a readable PDF: {exc}"
            ) from exc
        except _PYPDF_INTERNAL_ERRORS as exc:
            # Also catches a bug in our own visitor; the traceback keeps it
            # findable while the client gets a 400 for a file pypdf choked on.
            logger.warning(f"pypdf failed on upload: {exc!r}", exc_info=True)
            raise InvalidDocumentError(
                "Uploaded file is not a readable PDF."
            ) from exc
        return "\n\n".join(text for text in pages if text)


def _extract_page(page: PageObject) -> str:
    # Plain mode keeps reading order (columns stay separate) but joins every
    # line with a single "\n", losing paragraph boundaries. The visitor
    # exposes each fragment's position, so the vertical gaps can be read.
    lines: list[TextLine] = []
    parts: list[str] = []
    y: float | None = None
    size = 0.0

    def visit(
        text: str,
        cm: list[float],
        tm: list[float],
        font_dict: object,
        font_size: float,
    ) -> None:
        nonlocal y, size
        for i, piece in enumerate(text.split("\n")):
            if i > 0:
                _flush_line(lines, parts, y, size)
                y = None
            if piece.strip() and y is None:
                # Baseline of the text matrix mapped into page space.
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                size = font_size * math.hypot(tm[2], tm[3])
                size *= math.hypot(cm[2], cm[3])
            parts.append(piece)

    page.extract_text(visitor_text=visit)
    _flush_line(lines, parts, y, size)
    return join_lines(lines)


def _flush_line(
    lines: list[TextLine], parts: list[str], y: float | None, size: float
) -> None:
    text = "".join(parts).strip()
    parts.clear()
    if text and y is not None:
        lines.append(TextLine(text, y, size))


def join_lines(lines: list[TextLine]) -> str:
    """Join lines, inserting a blank line wherever a paragraph break is."""
    spacings = [_spacing(above, below) for above, below in pairwise(lines)]
    tight = [s for s in spacings if s >= _MIN_LINE_SPACING]
    threshold = _MAX_LINE_SPACING
    if tight:
        threshold = min(min(tight) * _PARAGRAPH_GAP_FACTOR, threshold)

    out = [lines[0].text] if lines else []
    for line, spacing in zip(lines[1:], spacings, strict=True):
        is_break = spacing < _JUMP_UP_SPACING or spacing > threshold
        out.append("\n\n" if is_break else "\n")
        out.append(line.text)
    return "".join(out)


def _spacing(above: TextLine, below: TextLine) -> float:
    if below.font_size <= 0:
        return 0.0
    return (above.y - below.y) / below.font_size
