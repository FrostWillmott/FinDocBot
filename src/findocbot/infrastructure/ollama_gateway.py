"""Ollama implementation for model provider gateway."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from findocbot.domain.exceptions import ModelProviderError


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
    ) -> None:
        """Store Ollama endpoint settings and model names."""
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout = timeout_seconds
        self._batch_size = batch_size
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
        """POST to Ollama; transport errors become ModelProviderError."""
        client = self._get_client()
        try:
            response = await client.post(
                f"{self._base_url}{path}", json=json_body
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelProviderError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ModelProviderError(
                f"Ollama unreachable at {self._base_url}"
            ) from exc
        return response

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
