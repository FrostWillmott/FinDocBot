"""Tests for the shared test factories."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo

import pytest

from tests.factories import build_pdf_bytes


class _AnyDatetime(type):
    """Lets a clock stand in for ``datetime`` where fpdf type-checks dates."""

    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, datetime)


class _TickingClock(datetime, metaclass=_AnyDatetime):
    """A clock that moves one second on every ``now()``."""

    ticks = 0

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _TickingClock:
        cls.ticks += 1
        return cls(2026, 1, 1, 0, 0, cls.ticks, tzinfo=tz or UTC)


def test_build_pdf_bytes_same_text_across_clock_ticks_returns_identical_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("fpdf.fpdf.datetime", _TickingClock)

    assert build_pdf_bytes("Revenue grew.") == build_pdf_bytes("Revenue grew.")
