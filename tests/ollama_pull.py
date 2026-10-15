"""Pull Ollama models in the e2e container, retrying registry errors."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)

# ``ollama pull`` redraws a progress spinner with these escape sequences.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class _ExecResult(Protocol):
    exit_code: int
    output: bytes


class _Container(Protocol):
    def exec(self, command: list[str]) -> _ExecResult: ...


def _last_line(output: bytes) -> str:
    """The last readable line of ``ollama pull`` output: its error message."""
    text = _ANSI.sub("", output.decode(errors="replace"))
    lines = [line.strip() for line in re.split(r"[\r\n]", text)]
    return next((line for line in reversed(lines) if line), "(no output)")


def pull_model(
    container: _Container,
    model: str,
    *,
    attempts: int = 3,
    pause_seconds: float = 10.0,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    """Pull ``model``, retrying with a growing pause between attempts.

    The Ollama registry is an external service that now and then answers a
    transient 503; one such answer must not fail the whole e2e session. The
    exit code is checked on purpose (the container's own ``pull_model``
    discards it), so a pull that really failed surfaces here and not later as
    an unrelated embedding error.
    """
    for attempt in range(1, attempts + 1):
        result = container.exec(["ollama", "pull", model])
        if result.exit_code == 0:
            return
        reason = _last_line(result.output)
        logger.warning(
            "ollama pull %s failed (attempt %d of %d): %s",
            model,
            attempt,
            attempts,
            reason,
        )
        if attempt == attempts:
            raise RuntimeError(
                f"ollama pull {model} failed after {attempts} attempts: "
                f"{reason}"
            )
        pause(pause_seconds * attempt)
