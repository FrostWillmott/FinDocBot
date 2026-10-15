"""Pure scoring helpers for the retrieval evaluation."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

# What the reference Qwen3-Reranker code uses for a yes/no token that is
# missing from the returned top log-probabilities.
_MISSING_LOGPROB = -10.0


def yes_probability(top_logprobs: Iterable[tuple[str, float]]) -> float:
    """Return P(yes) among the yes/no answers at the first generated position.

    Every case and spacing variant of a token counts ("Yes", "yes", " yes"),
    because the tokenizer emits several of them and each carries probability
    mass; keeping only the last one seen drops most of it. A token missing
    from the list gets log-probability -10, as in the reference code.
    """
    yes: list[float] = []
    no: list[float] = []
    for token, logprob in top_logprobs:
        word = token.strip().lower()
        if word == "yes":
            yes.append(math.exp(logprob))
        elif word == "no":
            no.append(math.exp(logprob))
    yes_mass = sum(yes) if yes else math.exp(_MISSING_LOGPROB)
    no_mass = sum(no) if no else math.exp(_MISSING_LOGPROB)
    return yes_mass / (yes_mass + no_mass)


def hit_at(hits: Sequence[bool], k: int) -> bool:
    """Whether any of the first *k* ranked results is a hit."""
    return any(hits[:k])


def reciprocal_rank(hits: Sequence[bool]) -> float:
    """Return 1/rank of the first hit, or 0.0 when there is none."""
    for rank, hit in enumerate(hits, start=1):
        if hit:
            return 1 / rank
    return 0.0


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile of *values* (``fraction`` in 0..1)."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[max(index, 0)]


def contains_gold(text: str, gold: str) -> bool:
    """Whether *text* contains *gold*, ignoring how lines were wrapped.

    A figure can be split across a line break in the extracted PDF text, so
    whitespace is collapsed on both sides before comparing.
    """
    return " ".join(gold.split()) in " ".join(text.split())
