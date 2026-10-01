"""Neutralise untrusted text before it is placed into an LLM prompt."""

from __future__ import annotations

import re

# Prompts delimit untrusted spans with XML-like tags and attributes, so
# escaping these stops document text from closing or forging them.
_TAG_CHARS = str.maketrans({"<": "&lt;", ">": "&gt;", '"': "&quot;"})
_CODE_FENCE = re.compile(r"`{3,}")
_INJECTION_MARKER = re.compile(
    r"^[ \t]*(?:system|assistant|user|instructions?)\s*:"
    r"|\b(?:ignore|disregard|forget)\s+(?:all\s+)?"
    r"(?:the\s+)?(?:previous|prior|above)\b",
    re.IGNORECASE | re.MULTILINE,
)
_TRUNCATION_MARK = " [truncated]"


def neutralize(text: str, max_chars: int) -> str:
    """Truncate *text* and defuse markers that mimic prompt structure.

    Markers are wrapped rather than deleted so the original stays
    readable in logs and to the model as quoted content.
    """
    if len(text) > max_chars:
        text = text[:max_chars] + _TRUNCATION_MARK
    text = text.translate(_TAG_CHARS)
    text = _CODE_FENCE.sub(lambda m: "'" * len(m.group()), text)
    return _INJECTION_MARKER.sub(lambda m: f"[quoted: {m.group()}]", text)
