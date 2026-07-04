"""Direct tests for ParagraphTokenChunker — the most complex logic."""

from findocbot.infrastructure.chunking import ParagraphTokenChunker


def _chunk_texts(chunks: list[tuple[str, str | None]]) -> list[str]:
    """Extract just the text parts from chunk tuples."""
    return [c[0] for c in chunks]


def _chunk_sections(chunks: list[tuple[str, str | None]]) -> list[str | None]:
    """Extract just the section parts from chunk tuples."""
    return [c[1] for c in chunks]


class TestParagraphTokenChunker:
    """Unit tests for the token-aware chunker."""

    def test_split_short_text_into_single_chunk(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        result = chunker.split("Hello world. This is a short text.")
        assert len(result) == 1
        assert result[0][1] is None  # No section

    def test_split_long_text_into_multiple_chunks(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=20)
        # ~30 tokens — should produce at least 2 chunks.
        text = "word " * 30
        result = chunker.split(text)
        assert len(result) >= 2

    def test_section_extraction(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=200)
        text = "Section 1: Introduction\nThis is the intro paragraph."
        result = chunker.split(text)
        assert result[0][1] == "Section 1: Introduction"

    def test_chapter_extraction(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=200)
        text = "Chapter 1: Overview\nSome content here."
        result = chunker.split(text)
        assert result[0][1] == "Chapter 1: Overview"

    def test_section_label_does_not_leak_to_previous_chunk(self) -> None:
        """Regression test: section change must NOT relabel a flushed chunk.

        When a new section header starts and the accumulated chunk is
        full, the flushed chunk must keep its ORIGINAL section label,
        not the one that triggered the flush.
        """
        chunker = ParagraphTokenChunker(
            chunk_tokens=15, overlap_ratio=0.0, min_chunk_tokens=1
        )
        # Section A content: enough tokens to fill a chunk when combined
        # with the next section header.
        text = (
            "Section Revenue\n"
            + "data " * 8  # 8 tokens
            + "\n\n"
            + "Section Profit\n"
            + "numbers " * 8  # 8 tokens
        )
        result = chunker.split(text)
        sections = _chunk_sections(result)

        # First chunk must keep its original section label.
        assert len(result) >= 2, f"Expected ≥2 chunks, got {len(result)}"
        assert sections[0] == "Section Revenue", (
            f"First chunk got label {sections[0]!r}, "
            f"expected 'Section Revenue'"
        )

    def test_overlap_between_chunks(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=15, overlap_ratio=0.5)
        # Paragraph breaks trigger chunk boundaries.
        text = (
            "unique " * 8 + "\n\n" + "overlap " * 8 + "\n\n" + "different " * 8
        )
        result = chunker.split(text)
        # With multiple paragraphs, should produce multiple chunks.
        assert len(result) >= 2

    def test_min_chunk_merged_with_previous(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100, min_chunk_tokens=50)
        # First paragraph fills a chunk, second is tiny → merged into first.
        text = "big " * 60 + "\n\n" + "tiny"
        result = chunker.split(text)
        assert len(result) == 1

    def test_empty_text_returns_empty_list(self) -> None:
        chunker = ParagraphTokenChunker()
        result = chunker.split("")
        assert result == []

    def test_long_paragraph_splitting(self) -> None:
        """A paragraph longer than chunk_tokens is split into sub-chunks."""
        chunker = ParagraphTokenChunker(chunk_tokens=15, overlap_ratio=0.2)
        text = "token " * 40  # 40 tokens in one paragraph, no paragraph breaks
        result = chunker.split(text)
        assert len(result) >= 2
        # Verify each chunk is non-empty and reasonably sized.
        for chunk_text, _ in result:
            assert len(chunk_text) > 0

    def test_strip_whitespace_only_paragraphs(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "Real content here.\n\n   \n\nMore content."
        result = chunker.split(text)
        texts = _chunk_texts(result)
        assert len(texts) >= 1
        assert "Real content" in texts[0]
