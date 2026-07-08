"""Caching wrapper for embedding gateway."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from findocbot.use_cases.ports import ModelProviderGateway

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache performance metrics."""

    hits: int
    misses: int
    size: int
    max_size: int

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CachedEmbeddingGateway:
    """Wrapper that caches embeddings for repeated queries."""

    def __init__(
        self,
        gateway: ModelProviderGateway,
        cache_size: int = 1000,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store gateway and configure cache size and TTL."""
        self._gateway = gateway
        self._cache_size = cache_size
        self._ttl_seconds = ttl_seconds
        # Cache stores (embedding, timestamp) tuples
        self._cache: OrderedDict[str, tuple[list[float], float]] = (
            OrderedDict()
        )
        self._hits = 0
        self._misses = 0

        if cache_size > 10000:
            logger.warning(
                f"Large cache size configured: {cache_size}. "
                f"This may consume significant memory. "
                f"Consider using a smaller cache or implementing TTL."
            )

    async def start(self) -> None:
        """Initialize underlying gateway."""
        await self._gateway.start()

    async def stop(self) -> None:
        """Shutdown underlying gateway and clear cache."""
        stats = self.get_stats()
        logger.info(
            f"Cache stats: {stats.hits} hits, {stats.misses} misses, "
            f"hit rate: {stats.hit_rate:.2%}, final size: {stats.size}"
        )
        self._cache.clear()
        await self._gateway.stop()

    def _text_to_cache_key(self, text: str) -> str:
        """Convert text to deterministic cache key."""
        return sha256(text.encode("utf-8")).hexdigest()

    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry has expired based on TTL."""
        if self._ttl_seconds is None:
            return False
        return (time.time() - timestamp) > self._ttl_seconds

    async def embed_one(self, text: str) -> list[float]:
        """Embed single text with caching and TTL support."""
        cache_key = self._text_to_cache_key(text)

        if cache_key in self._cache:
            embedding, timestamp = self._cache[cache_key]

            if self._is_expired(timestamp):
                del self._cache[cache_key]
            else:
                self._cache.move_to_end(cache_key)
                self._hits += 1
                return embedding

        self._misses += 1
        # No single-flight lock here: concurrent identical misses may each
        # call the backend. Embeddings are idempotent, so the only cost is a
        # duplicate request — an accepted trade-off vs. per-key locking.
        result = await self._gateway.embed_one(text)

        self._cache[cache_key] = (result, time.time())

        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

        return result

    def get_stats(self) -> CacheStats:
        """Return current cache statistics."""
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=len(self._cache),
            max_size=self._cache_size,
        )

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts without caching (used for document chunks)."""
        return await self._gateway.embed_many(texts)

    async def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate structured response (pass-through to gateway)."""
        return await self._gateway.generate_structured(prompt, schema)
