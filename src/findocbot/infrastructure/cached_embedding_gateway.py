"""Caching wrapper for embedding gateway."""

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256

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
        gateway,
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

        # Warn about large cache sizes
        if cache_size > 10000:
            logger.warning(
                f"Large cache size configured: {cache_size}. "
                f"This may consume significant memory. "
                f"Consider using a smaller cache or implementing TTL."
            )

    async def start(self) -> None:
        """Initialize underlying gateway."""
        if hasattr(self._gateway, "start"):
            await self._gateway.start()

    async def stop(self) -> None:
        """Shutdown underlying gateway and clear cache."""
        stats = self.get_stats()
        logger.info(
            f"Cache stats: {stats.hits} hits, {stats.misses} misses, "
            f"hit rate: {stats.hit_rate:.2%}, final size: {stats.size}"
        )
        self._cache.clear()
        if hasattr(self._gateway, "stop"):
            await self._gateway.stop()

    def _text_to_cache_key(self, text: str) -> str:
        """Convert text to deterministic cache key."""
        return sha256(text.encode("utf-8")).hexdigest()

    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry has expired based on TTL."""
        if self._ttl_seconds is None:
            return False
        return (time.time() - timestamp) > self._ttl_seconds

    def _cleanup_expired(self) -> int:
        """Remove all expired entries from cache.

        Returns count of removed entries.
        """
        if self._ttl_seconds is None:
            return 0

        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if self._is_expired(timestamp)
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    async def embed_one(self, text: str) -> list[float]:
        """Embed single text with caching and TTL support."""
        cache_key = self._text_to_cache_key(text)

        # Check if result is in cache
        if cache_key in self._cache:
            embedding, timestamp = self._cache[cache_key]

            # Check if entry has expired
            if self._is_expired(timestamp):
                # Remove expired entry
                del self._cache[cache_key]
            else:
                # Move to end (mark as recently used)
                self._cache.move_to_end(cache_key)
                self._hits += 1
                return embedding

        # Compute embedding
        self._misses += 1
        result = await self._gateway.embed_one(text)

        # Add to cache with current timestamp
        self._cache[cache_key] = (result, time.time())

        # Evict oldest if cache is full
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

    async def generate(self, prompt: str) -> str:
        """Generate response (pass-through to underlying gateway)."""
        return await self._gateway.generate(prompt)
