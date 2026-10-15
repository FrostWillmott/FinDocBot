"""Tests that the synthetic retrieval-evaluation corpus is well formed."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from evals.retrieval_eval import IndexedChunk, load_chunks, validate
from evals.synthetic import (
    CATEGORIES,
    DEFAULT_QUESTIONS,
    QUESTIONS_PER_CATEGORY,
    Question,
    build_questions,
    build_reports,
    read_questions,
    render_pdf,
)
from findocbot.config import Settings


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> list[IndexedChunk]:
    pdf_dir = tmp_path_factory.mktemp("synthetic")
    for report in build_reports():
        (pdf_dir / report.filename).write_bytes(render_pdf(report))
    settings = Settings(
        _env_file=None, postgres_dsn="postgresql://u:p@localhost/db"
    )
    return load_chunks(pdf_dir, settings)


def test_committed_questions_match_the_generator() -> None:
    committed = read_questions(Path(DEFAULT_QUESTIONS))

    assert committed == build_questions(build_reports())


def test_questions_are_balanced_across_categories() -> None:
    questions = read_questions(Path(DEFAULT_QUESTIONS))

    assert Counter(q.category for q in questions) == dict.fromkeys(
        CATEGORIES, QUESTIONS_PER_CATEGORY
    )


def test_every_report_is_split_into_one_chunk_per_section(
    corpus: list[IndexedChunk],
) -> None:
    per_document = Counter(chunk.document for chunk in corpus)

    assert set(per_document.values()) == {6}


def test_every_gold_figure_is_in_exactly_one_chunk_of_the_right_report(
    corpus: list[IndexedChunk],
) -> None:
    questions = read_questions(Path(DEFAULT_QUESTIONS))

    validate(questions, corpus)  # raises SystemExit naming any bad question


def test_validate_rejects_a_gold_figure_that_appears_nowhere(
    corpus: list[IndexedChunk],
) -> None:
    missing = Question("q99", "x", "?", corpus[0].document, "USD 1 million")

    with pytest.raises(SystemExit, match="q99"):
        validate([missing], corpus)


def test_validate_any_accepts_a_figure_repeated_within_its_document() -> None:
    chunks = [
        IndexedChunk("a.pdf", "revenue was USD 5 million"),
        IndexedChunk("a.pdf", "again: USD 5 million, see above"),
    ]
    question = Question("q1", "x", "?", "a.pdf", "USD 5 million")

    validate([question], chunks, unique=False)  # raises SystemExit if invalid


def test_validate_unique_rejects_a_figure_repeated_within_its_document() -> (
    None
):
    chunks = [
        IndexedChunk("a.pdf", "revenue was USD 5 million"),
        IndexedChunk("a.pdf", "again: USD 5 million, see above"),
    ]
    question = Question("q1", "x", "?", "a.pdf", "USD 5 million")

    with pytest.raises(SystemExit, match="q1"):
        validate([question], chunks)


def test_validate_any_rejects_a_figure_found_in_another_document() -> None:
    chunks = [
        IndexedChunk("a.pdf", "revenue was USD 5 million"),
        IndexedChunk("b.pdf", "profit was USD 5 million"),
    ]
    question = Question("q1", "x", "?", "a.pdf", "USD 5 million")

    with pytest.raises(SystemExit, match="q1"):
        validate([question], chunks, unique=False)
