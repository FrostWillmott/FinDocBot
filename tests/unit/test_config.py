"""Tests for Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from findocbot.config import Settings

_DSN = "postgresql://u:p@localhost:5432/db"


@pytest.mark.parametrize("ratio", [1.0, 1.5, -0.1])
def test_settings_chunk_overlap_ratio_out_of_range_raises_validation_error(
    ratio: float,
) -> None:
    with pytest.raises(ValidationError, match="chunk_overlap_ratio"):
        Settings(
            postgres_dsn=_DSN,  # type: ignore[arg-type]
            chunk_overlap_ratio=ratio,
            _env_file=None,  # type: ignore[call-arg]
        )


@pytest.mark.parametrize("tokens", [1, 0, -5])
def test_settings_chunk_tokens_below_two_raises_validation_error(
    tokens: int,
) -> None:
    with pytest.raises(ValidationError, match="chunk_tokens"):
        Settings(
            postgres_dsn=_DSN,  # type: ignore[arg-type]
            chunk_tokens=tokens,
            _env_file=None,  # type: ignore[call-arg]
        )


def test_settings_default_chunk_limits_are_valid() -> None:
    settings = Settings(
        postgres_dsn=_DSN,  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    assert (settings.chunk_tokens, settings.chunk_overlap_ratio) == (300, 0.15)
