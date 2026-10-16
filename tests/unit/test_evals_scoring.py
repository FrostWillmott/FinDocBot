"""Tests for the pure scoring helpers of the evaluations."""

from __future__ import annotations

import pytest

from evals.scoring import (
    answer_matches,
    contains_gold,
    hit_at,
    percentile,
    reciprocal_rank,
)


def test_hit_at_counts_only_the_first_k_results() -> None:
    hits = [False, False, True]

    assert (hit_at(hits, 2), hit_at(hits, 3)) == (False, True)


def test_reciprocal_rank_is_one_over_the_first_hit_rank() -> None:
    assert reciprocal_rank([False, False, True, True]) == pytest.approx(1 / 3)


def test_reciprocal_rank_without_a_hit_is_zero() -> None:
    assert reciprocal_rank([False, False]) == 0.0


def test_percentile_is_nearest_rank() -> None:
    values = [0.1 * n for n in range(1, 11)]

    assert percentile(values, 0.9) == pytest.approx(0.9)


def test_contains_gold_ignores_line_wrapping() -> None:
    assert contains_gold("revenue of USD 202\nmillion for", "USD 202 million")


def test_contains_gold_does_not_match_a_longer_figure() -> None:
    assert not contains_gold("revenue of USD 1,202 million", "USD 202 million")


def test_answer_matches_figure_with_other_separators_matches() -> None:
    assert answer_matches("Revenue was USD 1 284 million.", "1,284")


def test_answer_matches_a_different_figure_does_not_match() -> None:
    assert not answer_matches("Revenue was USD 1,285 million.", "1,284")


def test_answer_matches_a_figure_containing_the_gold_does_not_match() -> None:
    assert not answer_matches("Revenue was USD 1,202 million.", "202")


def test_answer_matches_gold_with_two_figures_needs_both() -> None:
    assert not answer_matches("3,730", "$ 3,730 $ 2,331")


def test_answer_matches_gold_with_two_figures_matches_when_both_appear() -> (
    None
):
    assert answer_matches("3,730 now and 2,331 before", "$ 3,730 $ 2,331")


def test_answer_matches_ignores_one_digit_numbers_in_the_gold() -> None:
    assert answer_matches("120 units", "within 5 years, 120 units")


def test_answer_matches_gold_without_figures_matches_the_name() -> None:
    assert answer_matches("The CEO is Greg Abel.", "Greg Abel")


def test_answer_matches_gold_without_figures_rejects_another_name() -> None:
    assert not answer_matches("The CEO is Warren Buffett.", "Greg Abel")
