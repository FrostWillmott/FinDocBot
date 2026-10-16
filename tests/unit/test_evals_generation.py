"""Tests for the report of the generation evaluation."""

from __future__ import annotations

from evals.generation_eval import Result, format_report


def _result(
    qid: str,
    *,
    report: str = "en",
    answerable: bool = True,
    matched: bool = True,
    answer: str = "an answer",
    error: str | None = None,
    generate_seconds: float = 2.0,
) -> Result:
    return Result(
        model="m1",
        report=report,
        question_id=qid,
        question=f"question {qid}?",
        gold="gold",
        answer=answer,
        error=error,
        answerable=answerable,
        matched=matched,
        seconds=generate_seconds + 0.5,
        generate_seconds=generate_seconds,
    )


def _report(results: list[Result]) -> str:
    return format_report(results, {"ollama": "0.1.0"}, top_k=5, label="t")


def test_format_report_summary_row_counts_answerable_and_matched() -> None:
    results = [
        _result("en01"),
        _result("en02", matched=False),
        _result("ru01", report="ru", answerable=False, matched=False),
    ]

    assert "| m1 | 2/3 | 1/2 | 0 |" in _report(results)


def test_format_report_summary_row_counts_followed_injections() -> None:
    results = [
        _result("inj1", report="injection", answerable=False, answer="HACKED"),
        _result(
            "inj2", report="injection", answerable=False, answer="USD 0.20"
        ),
    ]

    assert "| m1 | 0/0 | 0/0 | 0 | 1/2 |" in _report(results)


def test_format_report_summary_row_counts_errors() -> None:
    results = [
        _result("en01"),
        _result(
            "en02", answerable=False, matched=False, error="ModelProviderError"
        ),
    ]

    assert "| m1 | 1/2 | 1/1 | 1 |" in _report(results)


def test_format_report_median_generation_time_by_report() -> None:
    results = [
        _result("en01", generate_seconds=2.0),
        _result("en02", generate_seconds=4.0),
        _result("en03", generate_seconds=9.0),
    ]

    assert "| m1 | 4.0 |" in _report(results)


def test_format_report_lists_answerable_questions_the_check_missed() -> None:
    results = [
        _result("en01"),
        _result("en02", matched=False, answer="USD 3,000 million"),
        _result("en03", answerable=False, matched=False, answer="no idea"),
    ]

    report = _report(results)

    assert "USD 3,000 million" in report
    assert "no idea" not in report
