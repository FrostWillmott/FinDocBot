"""Tests for the pure scoring helpers of the retrieval evaluation."""

from __future__ import annotations

import math

import pytest

from evals.scoring import (
    contains_gold,
    hit_at,
    percentile,
    reciprocal_rank,
    yes_probability,
)


def _p(logprob_yes: float, logprob_no: float) -> float:
    yes, no = math.exp(logprob_yes), math.exp(logprob_no)
    return yes / (yes + no)


def test_yes_probability_normalises_over_yes_and_no_only() -> None:
    top = [("yes", math.log(0.3)), ("no", math.log(0.1)), ("1", math.log(0.5))]

    assert yes_probability(top) == pytest.approx(0.75)


def test_yes_probability_sums_every_case_and_spacing_variant() -> None:
    top = [
        ("No", math.log(0.41)),
        ("no", math.log(0.20)),
        (" yes", math.log(0.05)),
        ("Yes", math.log(0.03)),
    ]

    # Keeping only the last variant of each would give 0.03 / (0.03 + 0.20).
    assert yes_probability(top) == pytest.approx(0.08 / (0.08 + 0.61))


def test_yes_probability_missing_token_counts_as_logprob_minus_ten() -> None:
    assert yes_probability([("yes", -0.5)]) == pytest.approx(_p(-0.5, -10.0))


def test_yes_probability_neither_token_present_is_even() -> None:
    assert yes_probability([("maybe", -0.1)]) == pytest.approx(0.5)


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
