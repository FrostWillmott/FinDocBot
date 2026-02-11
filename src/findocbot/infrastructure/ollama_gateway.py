"""Ollama implementation for model provider gateway."""

import httpx


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

    async def embed_one(self, text: str) -> list[float]:
        """Embed single query text."""
        embeddings = await self.embed_many([text])
        return embeddings[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed many chunk texts with automatic batching."""
        if not texts:
            return []
        
        # Process in batches to avoid timeout on large documents
        all_embeddings: list[list[float]] = []
        client = self._get_client()
        
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={
                    "model": self._embed_model,
                    "input": batch,
                },
            )
            response.raise_for_status()
            payload = response.json()
            all_embeddings.extend(payload["embeddings"])
        
        return all_embeddings

    async def generate(self, prompt: str) -> str:
        """Generate answer from context-aware prompt."""
        client = self._get_client()
        response = await client.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._chat_model,
                "prompt": prompt,
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload["response"].strip()
