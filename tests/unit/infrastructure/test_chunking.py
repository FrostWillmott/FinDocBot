"""Direct tests for ParagraphTokenChunker — the most complex logic."""

from __future__ import annotations

import logging

import pytest

from findocbot.infrastructure.chunking import ParagraphTokenChunker


def _chunk_texts(chunks: list[tuple[str, str | None]]) -> list[str]:
    """Extract just the text parts from chunk tuples."""
    return [c[0] for c in chunks]


def _chunk_sections(chunks: list[tuple[str, str | None]]) -> list[str | None]:
    """Extract just the section parts from chunk tuples."""
    return [c[1] for c in chunks]


class TestParagraphTokenChunker:
    """Unit tests for the token-aware chunker."""

    def test_split_short_text_returns_one_unlabelled_chunk(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        result = chunker.split("Hello world. This is a short text.")
        assert len(result) == 1
        assert result[0][1] is None  # No section

    def test_split_text_over_budget_returns_several_chunks(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=20)
        # ~30 tokens — should produce at least 2 chunks.
        text = "word " * 30
        result = chunker.split(text)
        assert len(result) >= 2

    def test_split_section_heading_labels_chunk(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=200)
        text = "Section 1: Introduction\nThis is the intro paragraph."
        result = chunker.split(text)
        assert result[0][1] == "Section 1: Introduction"

    def test_split_chapter_heading_labels_chunk(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=200)
        text = "Chapter 1: Overview\nSome content here."
        result = chunker.split(text)
        assert result[0][1] == "Chapter 1: Overview"

    def test_split_new_section_keeps_previous_chunk_label(self) -> None:
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

    def test_split_paragraphs_over_budget_return_several_chunks(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=15, overlap_ratio=0.5)
        # Paragraph breaks trigger chunk boundaries.
        text = (
            "unique " * 8 + "\n\n" + "overlap " * 8 + "\n\n" + "different " * 8
        )
        result = chunker.split(text)
        # With multiple paragraphs, should produce multiple chunks.
        assert len(result) >= 2

    def test_split_tiny_last_paragraph_merges_into_previous_chunk(
        self,
    ) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100, min_chunk_tokens=50)
        # First paragraph fills a chunk, second is tiny → merged into first.
        text = "big " * 60 + "\n\n" + "tiny"
        result = chunker.split(text)
        assert len(result) == 1

    def test_split_empty_text_returns_empty_list(self) -> None:
        chunker = ParagraphTokenChunker()
        result = chunker.split("")
        assert result == []

    def test_split_oversized_paragraph_returns_non_empty_pieces(self) -> None:
        """A paragraph longer than chunk_tokens is split into sub-chunks."""
        chunker = ParagraphTokenChunker(chunk_tokens=15, overlap_ratio=0.2)
        text = "token " * 40  # 40 tokens in one paragraph, no paragraph breaks
        result = chunker.split(text)
        assert len(result) >= 2
        # Verify each chunk is non-empty and reasonably sized.
        for chunk_text, _ in result:
            assert len(chunk_text) > 0

    def test_split_oversized_paragraph_after_flush_merges_overlap(
        self,
    ) -> None:
        """A paragraph too big for the remaining budget after a flush is
        split immediately, with the overlap merged into its first piece
        instead of flushed as a duplicate overlap-only chunk."""
        chunker = ParagraphTokenChunker(
            chunk_tokens=10, overlap_ratio=0.5, min_chunk_tokens=1
        )
        para1 = "alpha beta gamma delta epsilon zeta eta theta"  # 8 tokens
        para2 = "one two three four five six seven eight nine"  # 9 tokens
        result = chunker.split(para1 + "\n\n" + para2)

        texts = _chunk_texts(result)
        assert len(texts) == 2
        assert texts[0] == para1
        # Second chunk = 5-token overlap from chunk 1 + the new paragraph.
        assert texts[1].startswith("delta epsilon zeta eta theta")
        assert texts[1].endswith(para2)

    def test_split_oversized_first_paragraph_keeps_section_label(self) -> None:
        """A first paragraph exceeding chunk_tokens is split into pieces
        that all carry its own section header."""
        chunker = ParagraphTokenChunker(
            chunk_tokens=8, overlap_ratio=0.25, min_chunk_tokens=1
        )
        text = "Section 9\n" + "word " * 20
        result = chunker.split(text)

        assert len(result) >= 2
        assert all(
            section == "Section 9" for section in _chunk_sections(result)
        )

    def test_split_whitespace_only_paragraph_is_dropped(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "Real content here.\n\n   \n\nMore content."
        result = chunker.split(text)
        texts = _chunk_texts(result)
        assert len(texts) >= 1
        assert "Real content" in texts[0]

    def test_split_oversized_paragraph_keeps_original_spacing(self) -> None:
        chunker = ParagraphTokenChunker(
            chunk_tokens=10, overlap_ratio=0.2, min_chunk_tokens=1
        )
        text = "Revenue reached USD 1,284 million, up 14.6% year on year. " * 3
        result = chunker.split(text)

        texts = _chunk_texts(result)
        assert len(texts) >= 2
        assert all(" , " not in t and " . " not in t for t in texts)
        assert texts[0] == "Revenue reached USD 1,284 million, up 14"

    def test_split_overlap_keeps_original_spacing(self) -> None:
        # 9-token overlap: "6,400 employees for their continued trust."
        chunker = ParagraphTokenChunker(
            chunk_tokens=22, overlap_ratio=0.41, min_chunk_tokens=1
        )
        para1 = "We thank our 6,400 employees for their continued trust."
        para2 = "Total revenue reached USD 1,284 million in fiscal 2025."
        result = chunker.split(para1 + "\n\n" + para2)

        texts = _chunk_texts(result)
        assert texts[1] == (
            "6,400 employees for their continued trust.\n\n" + para2
        )

    def test_split_section_heading_closes_previous_chunk(self) -> None:
        """Regression: a short heading used to fit into the tail of the
        previous section's chunk and relabel all of it."""
        chunker = ParagraphTokenChunker(
            chunk_tokens=100, overlap_ratio=0.2, min_chunk_tokens=5
        )
        intro = "Section 1. Letter\n\n" + "Growth was steady this year. " * 3
        highlights = "Section 2. Highlights\n\nNet profit was USD 132 million."
        result = chunker.split(intro + "\n\n" + highlights)

        assert result == [
            (intro.strip(), "Section 1. Letter"),
            (highlights, "Section 2. Highlights"),
        ]

    def test_split_heading_after_small_preamble_joins_preamble(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100, min_chunk_tokens=20)
        text = "Annual Report 2025\n\nSection 1. Letter\n\nGrowth was steady."
        result = chunker.split(text)

        assert result == [(text, "Section 1. Letter")]

    def test_split_overlap_mid_number_starts_at_word_boundary(self) -> None:
        chunker = ParagraphTokenChunker(
            chunk_tokens=12, overlap_ratio=0.45, min_chunk_tokens=1
        )
        para1 = "Revenue reached USD 1,284 million this year."
        para2 = "Outlook remains positive."
        result = chunker.split(para1 + "\n\n" + para2)

        # The 5-token window starts at "284" (mid "1,284"); it snaps to
        # "million".
        assert _chunk_texts(result)[1] == ("million this year.\n\n" + para2)


class TestCharacterCeiling:
    """No chunk is longer than ten characters per chunk token.

    The chunker counts words and marks, which says little about length for
    text without spaces or with its spaces lost.
    """

    def test_split_paragraphs_of_one_long_word_cap_every_chunk(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "\n\n".join(["x" * 600] * 8)  # 8 tokens to the chunker

        result = chunker.split(text)

        assert max(len(chunk) for chunk, _ in result) <= 1000

    def test_split_large_chunk_tokens_still_fit_a_source_in_the_prompt(
        self,
    ) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=500)  # 5,000 characters
        text = "\n\n".join(["x" * 4500] * 8)  # 8 tokens to the chunker

        result = chunker.split(text)

        assert max(len(chunk) for chunk, _ in result) <= 4000

    def test_init_capped_ceiling_logs_a_warning_with_the_resolved_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            ParagraphTokenChunker(chunk_tokens=500)

        assert [r.getMessage() for r in caplog.records] == [
            (
                "chunk_tokens=500 allows 5000 characters per chunk; capped at "
                "4000, the longest source the answer prompt carries"
            )
        ]

    def test_init_default_chunk_tokens_logs_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            ParagraphTokenChunker()

        assert caplog.records == []

    def test_split_capping_keeps_all_the_text(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "\n\n".join(["x" * 600] * 8)

        result = chunker.split(text)

        assert sum(chunk.count("x") for chunk, _ in result) == 8 * 600

    def test_split_capping_prefers_paragraph_breaks(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "\n\n".join(["x" * 400] * 10)

        result = chunker.split(text)

        # Two whole paragraphs and the break between them, five times.
        assert [len(chunk) for chunk, _ in result] == [802] * 5

    def test_split_capping_keeps_the_section_of_every_piece(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)
        text = "Section 1. Notes\n\n" + "\n\n".join(["x" * 600] * 8)

        result = chunker.split(text)

        assert {section for _, section in result} == {"Section 1. Notes"}

    def test_split_one_unbreakable_run_is_cut_at_the_ceiling(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=100)

        result = chunker.split("x" * 2500)

        assert [len(chunk) for chunk, _ in result] == [1000, 1000, 500]

    def test_split_capping_cuts_at_a_space_not_inside_a_word(self) -> None:
        chunker = ParagraphTokenChunker(chunk_tokens=1000, max_chunk_chars=500)

        result = chunker.split("word " * 400)

        assert {w for chunk, _ in result for w in chunk.split()} == {"word"}

    def test_split_text_within_the_ceiling_is_unchanged(self) -> None:
        text = "\n\n".join(
            f"Section {n}. Revenue grew by {n} percent. " * 12
            for n in range(1, 9)
        )
        default = ParagraphTokenChunker(chunk_tokens=60)
        unbounded = ParagraphTokenChunker(
            chunk_tokens=60, max_chunk_chars=10**9
        )

        assert default.split(text) == unbounded.split(text)
