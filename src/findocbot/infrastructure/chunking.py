"""Token-oriented chunking with paragraph awareness."""

import re

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SECTION_PATTERN = re.compile(r"^(section|chapter)\b", re.IGNORECASE)


class ParagraphTokenChunker:
    """Split text into chunks while preserving paragraph/section boundaries."""

    def __init__(
        self,
        chunk_tokens: int = 300,
        overlap_ratio: float = 0.15,
        min_chunk_tokens: int = 80,
    ) -> None:
        """Initialize token limits and overlap for chunk building."""
        self._chunk_tokens = chunk_tokens
        self._overlap_tokens = max(1, int(chunk_tokens * overlap_ratio))
        self._min_chunk_tokens = min_chunk_tokens

    def split(self, text: str) -> list[tuple[str, str | None]]:
        """Return chunks as (text, section) pairs."""
        paragraphs = [
            p.strip() for p in re.split(r"\n{2,}", text) if p.strip()
        ]
        chunks: list[tuple[str, str | None]] = []
        current_parts: list[str] = []
        current_section: str | None = None

        for paragraph in paragraphs:
            maybe_section = self._extract_section(paragraph)
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
                chunks.append((chunk_text, current_section))
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
                chunks.append((last_chunk, current_section))
            else:
                merged_text = "\n\n".join([chunks[-1][0], last_chunk]).strip()
                chunks[-1] = (merged_text, chunks[-1][1])
        return chunks

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
        tokens = TOKEN_PATTERN.findall(paragraph)
        if len(tokens) <= self._chunk_tokens:
            return [(paragraph, section)]

        parts: list[tuple[str, str | None]] = []
        start = 0
        while start < len(tokens):
            end = min(len(tokens), start + self._chunk_tokens)
            piece = " ".join(tokens[start:end]).strip()
            if piece:
                parts.append((piece, section))
            if end >= len(tokens):
                break
            start = max(0, end - self._overlap_tokens)
        return parts

    def _build_overlap(self, chunk_text: str) -> list[str]:
        overlap_tokens = TOKEN_PATTERN.findall(chunk_text)[
            -self._overlap_tokens :
        ]
        if not overlap_tokens:
            return []
        return [" ".join(overlap_tokens)]

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    @staticmethod
    def _extract_section(paragraph: str) -> str | None:
        first_line = paragraph.splitlines()[0].strip()
        if SECTION_PATTERN.match(first_line):
            return first_line
        return None
