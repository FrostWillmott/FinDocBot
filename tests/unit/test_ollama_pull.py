"""Tests for the e2e helper that pulls Ollama models with retries."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.ollama_pull import pull_model

# What a failed pull prints: redrawn spinner frames, then the error on a line.
_SPINNER = b"\x1b[?25l\x1b[1Gpulling manifest \xe2\xa0\x8b \x1b[K" * 3 + b"\n"
_REGISTRY_503 = (
    b"Error: pull model manifest: 503: upstream connect error or "
    b"disconnect/reset before headers. reset reason: connection termination\n"
)


@dataclass
class _Result:
    exit_code: int
    output: bytes


class _FakeContainer:
    """Answers each exec with the next scripted result."""

    def __init__(self, *results: _Result) -> None:
        self._results = list(results)
        self.commands: list[list[str]] = []

    def exec(self, command: list[str]) -> _Result:
        self.commands.append(command)
        return self._results.pop(0)


def test_pull_model_first_attempt_succeeds_runs_once() -> None:
    container = _FakeContainer(_Result(0, b""))
    pauses: list[float] = []

    pull_model(container, "m:1", pause=pauses.append)

    assert (container.commands, pauses) == ([["ollama", "pull", "m:1"]], [])


def test_pull_model_transient_failure_then_success_retries_once() -> None:
    container = _FakeContainer(
        _Result(1, _SPINNER + _REGISTRY_503), _Result(0, b"")
    )
    pauses: list[float] = []

    pull_model(container, "m:1", pause_seconds=10, pause=pauses.append)

    assert (len(container.commands), pauses) == (2, [10])


def test_pull_model_every_attempt_fails_raises_with_the_error_line() -> None:
    container = _FakeContainer(*[_Result(1, _SPINNER + _REGISTRY_503)] * 3)
    pauses: list[float] = []

    with pytest.raises(RuntimeError) as raised:
        pull_model(container, "m:1", pause_seconds=10, pause=pauses.append)

    assert (str(raised.value), len(container.commands), pauses) == (
        (
            "ollama pull m:1 failed after 3 attempts: Error: pull model "
            "manifest: 503: upstream connect error or disconnect/reset before "
            "headers. reset reason: connection termination"
        ),
        3,
        [10, 20],
    )


def test_pull_model_failure_without_output_says_so() -> None:
    container = _FakeContainer(_Result(1, b""))

    with pytest.raises(RuntimeError, match=r"1 attempts: \(no output\)"):
        pull_model(container, "m:1", attempts=1, pause=lambda _: None)
