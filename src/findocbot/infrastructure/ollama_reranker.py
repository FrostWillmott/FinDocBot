"""Ollama implementation of the reranker port (Qwen3-Reranker style)."""

from __future__ import annotations

import math
from collections.abc import Iterable

import httpx

from findocbot.domain.exceptions import ModelProviderError
from findocbot.use_cases.prompt_safety import neutralize

# Same limits as the answer prompt applies to the same untrusted text.
_MAX_QUERY_CHARS = 2000
_MAX_PASSAGE_CHARS = 4000
# Explicit, because the community GGUF defaults to a 40200-token window and
# Ollama then allocates an 8.7 GB runner for a 2.5 GB model (3.8 GB at 8192,
# measured); it also covers the longest prompt the limits above allow.
_NUM_CTX = 8192
# The reranker's own instruction (the model card's default): it is what the
# model was trained with, and the evaluation harness measured it.
DEFAULT_INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the "
    "query"
)
_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    "based on the Query and the Instruct provided. Note that the answer can "
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
# What the reference Qwen3-Reranker code uses for a yes/no token that is
# missing from the returned top log-probabilities.
_MISSING_LOGPROB = -10.0


def yes_probability(top_logprobs: Iterable[tuple[str, float]]) -> float:
    """Return P(yes) among the yes/no answers at the first generated position.

    Every case and spacing variant of a token counts ("Yes", "yes", " yes"),
    because the tokenizer emits several of them and each carries probability
    mass; keeping only the last one seen drops most of it. A token missing
    from the list gets log-probability -10, as in the reference code, so a
    reply with neither scores 0.5 instead of dividing by zero.
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


def reranker_prompt(
    query: str, passage: str, instruction: str = DEFAULT_INSTRUCTION
) -> str:
    """The Qwen3-Reranker prompt; the untrusted text is neutralised."""
    safe_query = neutralize(query, _MAX_QUERY_CHARS)
    safe_passage = neutralize(passage, _MAX_PASSAGE_CHARS)
    return (
        f"{_PREFIX}<Instruct>: {instruction}\n<Query>: {safe_query}\n"
        f"<Document>: {safe_passage}{_SUFFIX}"
    )


class OllamaReranker:
    """Score passages against a query with a reranker model on Ollama."""

    def __init__(
        self, base_url: str, model: str, timeout_seconds: float = 60.0
    ) -> None:
        """Store the Ollama endpoint, the reranker model and the timeout."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Return P(yes) for each passage, in the passages' order."""
        scores = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for passage in passages:
                scores.append(await self._score(client, query, passage))
        return scores

    async def _score(
        self, client: httpx.AsyncClient, query: str, passage: str
    ) -> float:
        try:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": reranker_prompt(query, passage),
                    "raw": True,
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 1,
                        "num_ctx": _NUM_CTX,
                    },
                    "logprobs": True,
                    "top_logprobs": 20,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelProviderError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ModelProviderError(
                f"Ollama timed out at {self._base_url}"
            ) from exc
        except httpx.TransportError as exc:
            raise ModelProviderError(
                f"Ollama unreachable at {self._base_url}"
            ) from exc
        try:
            top = [
                (entry["token"], entry["logprob"])
                for entry in response.json()["logprobs"][0]["top_logprobs"]
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError(
                "Ollama reply has no usable logprobs; the server may be too "
                "old to report them"
            ) from exc
        return yes_probability(top)
