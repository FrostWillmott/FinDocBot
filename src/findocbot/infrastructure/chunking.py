"""Token-oriented chunking with paragraph awareness."""

from __future__ import annotations

import logging
import re

from findocbot.use_cases.prompt_safety import MAX_SOURCE_CHARS

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
# Heading words of the reports in evals/documents.md (en/ru/hy). The
# first-line-only guard in _extract_section keeps these from matching body
# text, and \b keeps prefixes like "разделение" from matching "раздел".
SECTION_PATTERN = re.compile(
    r"^(section|chapter|раздел|բաժին)\b", re.IGNORECASE
)

# Characters per chunk token. The chunker counts words and marks, which says
# little about length: text without spaces (Thai, Chinese) or with its spaces
# lost in extraction is a handful of "tokens" however long it is. Measured
# with the embedder's tokenizer, a 300-token chunk is at most 2,343 characters
# in English, Russian and Armenian reports, so this keeps their chunks as they
# were and bounds every other script.
_MAX_CHARS_PER_TOKEN = 10
# A cut may move back by up to half the ceiling to land on a boundary.
_CUT_SEARCH_FLOOR = 0.5
# Where to cut, best first: paragraph, line, sentence mark, space.
_CUT_AFTER = ("\n\n", "\n", "。", ". ", " ")


class ParagraphTokenChunker:
    """Split text into chunks while preserving paragraph/section boundaries."""

    def __init__(
        self,
        chunk_tokens: int = 300,
        overlap_ratio: float = 0.15,
        min_chunk_tokens: int = 80,
        max_chunk_chars: int | None = None,
    ) -> None:
        """Initialize token limits and overlap for chunk building.

        ``max_chunk_chars`` is the ceiling on a chunk's length; by default
        ten characters per chunk token, but never more than a source can
        carry in the answer prompt (a longer chunk would be cut there, and
        the cut part could not be found by search).
        """
        self._chunk_tokens = chunk_tokens
        if max_chunk_chars is None:
            max_chunk_chars = chunk_tokens * _MAX_CHARS_PER_TOKEN
            if max_chunk_chars > MAX_SOURCE_CHARS:
                logger.warning(
                    "chunk_tokens=%d allows %d characters per chunk; capped "
                    "at %d, the longest source the answer prompt carries",
                    chunk_tokens,
                    max_chunk_chars,
                    MAX_SOURCE_CHARS,
                )
                max_chunk_chars = MAX_SOURCE_CHARS
        self._max_chars = max_chunk_chars
        self._overlap_tokens = max(1, int(chunk_tokens * overlap_ratio))
        self._min_chunk_tokens = min_chunk_tokens

    def split(self, text: str) -> list[tuple[str, str | None]]:
        """Return chunks as (text, section) pairs, none over the ceiling."""
        return [
            (piece, section)
            for chunk, section in self._split_by_tokens(text)
            for piece in self._cap(chunk)
        ]

    def _cap(self, chunk: str) -> list[str]:
        """Cut *chunk* into pieces of at most ``max_chunk_chars``."""
        pieces: list[str] = []
        rest = chunk
        while len(rest) > self._max_chars:
            cut = self._cut_point(rest)
            pieces.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if rest:
            pieces.append(rest)
        return [piece for piece in pieces if piece] or [chunk]

    def _cut_point(self, text: str) -> int:
        """Where to cut *text*: after a boundary, else at the ceiling."""
        window = text[: self._max_chars]
        floor = int(self._max_chars * _CUT_SEARCH_FLOOR)
        for boundary in _CUT_AFTER:
            index = window.rfind(boundary, floor)
            if index != -1:
                return index + len(boundary)
        return self._max_chars

    def _split_by_tokens(self, text: str) -> list[tuple[str, str | None]]:
        paragraphs = [
            p.strip() for p in re.split(r"\n{2,}", text) if p.strip()
        ]
        chunks: list[tuple[str, str | None]] = []
        current_parts: list[str] = []
        current_section: str | None = None

        for paragraph in paragraphs:
            maybe_section = self._extract_section(paragraph)
            closed = self._close_before_section(maybe_section, current_parts)
            if closed is not None:
                chunks.append((
                    closed,
                    self._section_of(current_parts, current_section),
                ))
                current_parts = []
            candidate = "\n\n".join([*current_parts, paragraph]).strip()
            if self._count_tokens(candidate) <= self._chunk_tokens:
                current_parts.append(paragraph)
                if maybe_section is not None:
                    current_section = maybe_section
                continue

            if current_parts:
                chunk_text = "\n\n".join(current_parts).strip()
                # Use the section that was active *before* this paragraph
                # (current_section has not been updated yet).
                chunks.append((
                    chunk_text,
                    self._section_of(current_parts, current_section),
                ))
                current_parts = self._build_overlap(chunk_text)

                # If the incoming paragraph does not fit within the
                # remaining token budget, split it immediately and
                # merge the overlap into the first piece.  This avoids
                # flushing a duplicate overlap-only chunk and prevents
                # an oversized final chunk.
                handled = self._try_split_oversized_after_flush(
                    paragraph=paragraph,
                    maybe_section=maybe_section,
                    current_parts=current_parts,
                    current_section=current_section,
                )
                if handled is not None:
                    chunks.extend(handled[0])
                    current_parts = handled[1]
                    current_section = handled[2]
                    continue
            else:
                if maybe_section is not None:
                    current_section = maybe_section
                chunks.extend(
                    self._split_long_paragraph(paragraph, current_section)
                )
                continue

            # Only now update the section for the new paragraph being added.
            current_section, current_parts = self._append_to_current(
                paragraph=paragraph,
                maybe_section=maybe_section,
                current_parts=current_parts,
                current_section=current_section,
            )

        if current_parts:
            last_chunk = "\n\n".join(current_parts).strip()
            if (
                self._count_tokens(last_chunk) >= self._min_chunk_tokens
                or not chunks
            ):
                chunks.append((
                    last_chunk,
                    self._section_of(current_parts, current_section),
                ))
            else:
                merged_text = "\n\n".join([chunks[-1][0], last_chunk]).strip()
                prev_section = chunks[-1][1]
                last_section = self._section_of(current_parts, current_section)
                chunks[-1] = (
                    merged_text,
                    last_section if prev_section == last_section else None,
                )
        return chunks

    def _close_before_section(
        self,
        maybe_section: str | None,
        current_parts: list[str],
    ) -> str | None:
        """Return the running chunk's text if a heading should close it.

        Otherwise a short heading fits into the previous section's tail and
        relabels it. No overlap is carried across: a section boundary is a
        topic boundary. Too-small leftovers (e.g. a title page) join the
        section instead.
        """
        if maybe_section is None or not current_parts:
            return None
        current_text = "\n\n".join(current_parts).strip()
        if self._count_tokens(current_text) < self._min_chunk_tokens:
            return None
        return current_text

    @staticmethod
    def _append_to_current(
        paragraph: str,
        maybe_section: str | None,
        current_parts: list[str],
        current_section: str | None,
    ) -> tuple[str | None, list[str]]:
        """Update section and append *paragraph* to *current_parts*."""
        section = (
            maybe_section if maybe_section is not None else current_section
        )
        if paragraph not in current_parts:
            current_parts.append(paragraph)
        return section, current_parts

    def _try_split_oversized_after_flush(
        self,
        paragraph: str,
        maybe_section: str | None,
        current_parts: list[str],
        current_section: str | None,
    ) -> tuple[list[tuple[str, str | None]], list[str], str | None] | None:
        """Split *paragraph* if it exceeds the remaining token budget.

        Called right after flushing *current_parts* and building the
        overlap.  Returns new pieces, updated *current_parts*, and
        updated *current_section* when a split was performed, or
        ``None`` when the paragraph fits and should be appended normally.
        """
        overlap_size = (
            self._count_tokens("\n\n".join(current_parts))
            if current_parts
            else 0
        )
        if self._count_tokens(paragraph) <= self._chunk_tokens - overlap_size:
            return None

        section = (
            maybe_section if maybe_section is not None else current_section
        )
        pieces = self._split_long_paragraph(paragraph, section)
        if pieces and current_parts:
            first_text, first_section = pieces[0]
            merged = "\n\n".join([*current_parts, first_text]).strip()
            pieces[0] = (merged, first_section)
            current_parts = []
        return pieces, current_parts, section

    def _split_long_paragraph(
        self,
        paragraph: str,
        section: str | None,
    ) -> list[tuple[str, str | None]]:
        tokens = list(TOKEN_PATTERN.finditer(paragraph))
        if len(tokens) <= self._chunk_tokens:
            return [(paragraph, section)]

        parts: list[tuple[str, str | None]] = []
        start = 0
        while start < len(tokens):
            end = min(len(tokens), start + self._chunk_tokens)
            # Slice the source text rather than re-joining tokens, so the
            # original spacing survives ("6,400", not "6 , 400").
            piece = paragraph[
                tokens[start].start() : tokens[end - 1].end()
            ].strip()
            if piece:
                parts.append((piece, section))
            if end >= len(tokens):
                break
            start = max(0, end - self._overlap_tokens)
        return parts

    def _build_overlap(self, chunk_text: str) -> list[str]:
        overlap_tokens = list(TOKEN_PATTERN.finditer(chunk_text))[
            -self._overlap_tokens :
        ]
        if not overlap_tokens:
            return []
        # Start at a word boundary so the overlap never opens mid-number
        # (",284 million" from "1,284"); the skipped tokens are duplicated
        # content anyway.
        start = next(
            (
                token.start()
                for token in overlap_tokens
                if token.start() == 0
                or chunk_text[token.start() - 1].isspace()
            ),
            overlap_tokens[0].start(),
        )
        return [chunk_text[start:]]

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    @staticmethod
    def _extract_section(paragraph: str) -> str | None:
        first_line = paragraph.splitlines()[0].strip()
        if SECTION_PATTERN.match(first_line):
            return first_line
        return None

    def _section_of(
        self, paragraphs: list[str], fallback: str | None
    ) -> str | None:
        """The single section these paragraphs belong to, else None.

        A chunk that accumulated several headings (short sections merged
        under ``min_chunk_tokens``) has no one label; ``fallback`` is the
        active section for paragraphs that carry no heading of their own.
        """
        sections = {self._extract_section(p) for p in paragraphs}
        sections.discard(None)
        if len(sections) > 1:
            return None
        return fallback
