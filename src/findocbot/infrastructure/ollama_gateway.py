"""Ollama implementation for model provider gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ValidationError

from findocbot.domain.exceptions import ModelProviderError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class _EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class _GenerateResponse(BaseModel):
    response: str


class OllamaGateway:
    """Call Ollama chat and embedding endpoints."""

    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout_seconds: float = 120.0,
        batch_size: int = 50,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Store Ollama endpoint settings, model names and retry policy."""
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout = timeout_seconds
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize persistent HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    async def stop(self) -> None:
        """Close HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return active client or raise error."""
        if self._client is None:
            raise RuntimeError(
                "OllamaGateway not started. Call start() before use."
            )
        return self._client

    async def _post(
        self, path: str, json_body: dict[str, object]
    ) -> httpx.Response:
        """POST to Ollama, retrying transient failures with backoff.

        429/5xx and connection errors are retried; other HTTP errors fail
        at once. The bounded attempts double as the circuit breaker for
        batch loops, which abort on the first call that exhausts them.
        Timeouts are not retried: a slow generation would otherwise hold
        the request for several timeout periods.
        """
        client = self._get_client()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await client.post(
                    f"{self._base_url}{path}", json=json_body
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if (
                    status not in _RETRYABLE_STATUS
                    or attempt == self._max_attempts
                ):
                    raise ModelProviderError(
                        f"Ollama returned HTTP {status}"
                    ) from exc
                reason = f"HTTP {status}"
            except httpx.ConnectError as exc:
                if attempt == self._max_attempts:
                    raise ModelProviderError(
                        f"Ollama unreachable at {self._base_url}"
                    ) from exc
                reason = "connection error"
            except httpx.TimeoutException as exc:
                raise ModelProviderError(
                    f"Ollama timed out at {self._base_url}"
                ) from exc
            delay = self._backoff_seconds * 2 ** (attempt - 1)
            delay += random.uniform(0, delay / 2)
            logger.warning(
                f"Ollama {path} failed ({reason}); retry "
                f"{attempt}/{self._max_attempts - 1} in {delay:.2f}s"
            )
            await self._sleep(delay)

    async def embed_one(self, text: str) -> list[float]:
        """Embed single query text."""
        embeddings = await self.embed_many([text])
        return embeddings[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed many chunk texts with automatic batching."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = await self._post(
                "/api/embed",
                {"model": self._embed_model, "input": batch},
            )
            try:
                payload = _EmbedResponse.model_validate_json(response.content)
            except ValidationError as exc:
                raise ModelProviderError(
                    "Ollama returned malformed embeddings"
                ) from exc
            all_embeddings.extend(payload.embeddings)

        if len(all_embeddings) != len(texts):
            raise ModelProviderError(
                f"Ollama returned {len(all_embeddings)} embeddings "
                f"for {len(texts)} inputs"
            )

        return all_embeddings

    async def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate JSON response constrained to the given JSON Schema.

        Uses Ollama's ``format`` field to enforce structured output so the
        caller receives a parsed dict rather than raw text.
        """
        response = await self._post(
            "/api/generate",
            {
                "model": self._chat_model,
                "prompt": prompt,
                "stream": False,
                "format": schema,
            },
        )
        try:
            payload = _GenerateResponse.model_validate_json(response.content)
            result = json.loads(payload.response)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ModelProviderError(
                "Ollama returned malformed structured output"
            ) from exc
        if not isinstance(result, dict):
            raise ModelProviderError(
                "Ollama structured output is not a JSON object"
            )
        return result
