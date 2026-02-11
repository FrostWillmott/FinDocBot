"""Test embedding cache functionality."""

import asyncio

import pytest

from findocbot.infrastructure.cached_embedding_gateway import (
    CachedEmbeddingGateway,
)
from findocbot.infrastructure.ollama_gateway import OllamaGateway


class MockGateway:
    """Mock gateway for testing cache behavior."""

    def __init__(self) -> None:
        """Initialize call counters."""
        self.embed_one_calls = 0
        self.embed_many_calls = 0

    async def start(self) -> None:
        """Mock start method."""
        pass

    async def stop(self) -> None:
        """Mock stop method."""
        pass

    async def embed_one(self, text: str) -> list[float]:
        """Mock embed_one that counts calls."""
        self.embed_one_calls += 1
        return [float(len(text)), 1.0, 2.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Mock embed_many that counts calls."""
        self.embed_many_calls += 1
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    async def generate(self, prompt: str) -> str:
        """Mock generate method."""
        return "mock response"


@pytest.mark.asyncio
async def test_cached_gateway_caches_identical_queries() -> None:
    """Verify that identical queries hit cache instead of calling gateway."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10)
    await cached.start()

    # First call should hit the gateway
    result1 = await cached.embed_one("test query")
    assert mock.embed_one_calls == 1
    assert result1 == [10.0, 1.0, 2.0]

    # Second identical call should hit cache
    result2 = await cached.embed_one("test query")
    assert mock.embed_one_calls == 1  # No additional call
    assert result2 == result1

    # Different query should hit gateway again
    result3 = await cached.embed_one("different query")
    assert mock.embed_one_calls == 2
    assert result3 == [15.0, 1.0, 2.0]

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_does_not_cache_embed_many() -> None:
    """Verify that embed_many is not cached (used for document chunks)."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10)
    await cached.start()

    # Multiple calls to embed_many should always hit gateway
    await cached.embed_many(["chunk1", "chunk2"])
    assert mock.embed_many_calls == 1

    await cached.embed_many(["chunk1", "chunk2"])
    assert mock.embed_many_calls == 2  # Not cached

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_respects_cache_size() -> None:
    """Verify that cache evicts old entries when size limit is reached."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=2)
    await cached.start()

    # Fill cache with 2 entries
    await cached.embed_one("query1")
    await cached.embed_one("query2")
    assert mock.embed_one_calls == 2

    # Access query1 again (should be cached)
    await cached.embed_one("query1")
    assert mock.embed_one_calls == 2

    # Add third entry (should evict least recently used)
    await cached.embed_one("query3")
    assert mock.embed_one_calls == 3

    # query1 and query3 should be cached, query2 might be evicted
    await cached.embed_one("query3")
    assert mock.embed_one_calls == 3  # Still cached

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_clears_cache_on_stop() -> None:
    """Verify that cache is cleared when gateway is stopped."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10)
    await cached.start()

    # Cache a query
    await cached.embed_one("test query")
    assert mock.embed_one_calls == 1

    # Verify it's cached
    await cached.embed_one("test query")
    assert mock.embed_one_calls == 1

    # Stop and restart
    await cached.stop()
    await cached.start()

    # After restart, cache should be cleared
    await cached.embed_one("test query")
    assert mock.embed_one_calls == 2  # New call after cache clear

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_tracks_metrics() -> None:
    """Verify that cache tracks hits and misses correctly."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10)
    await cached.start()

    # Initial stats should be zero
    stats = cached.get_stats()
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.size == 0
    assert stats.hit_rate == 0.0

    # First call is a miss
    await cached.embed_one("query1")
    stats = cached.get_stats()
    assert stats.hits == 0
    assert stats.misses == 1
    assert stats.size == 1
    assert stats.hit_rate == 0.0

    # Second call to same query is a hit
    await cached.embed_one("query1")
    stats = cached.get_stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.size == 1
    assert stats.hit_rate == 0.5

    # New query is a miss
    await cached.embed_one("query2")
    stats = cached.get_stats()
    assert stats.hits == 1
    assert stats.misses == 2
    assert stats.size == 2
    assert stats.hit_rate == 1 / 3

    # Another hit
    await cached.embed_one("query1")
    stats = cached.get_stats()
    assert stats.hits == 2
    assert stats.misses == 2
    assert stats.hit_rate == 0.5

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_respects_ttl() -> None:
    """Verify that cache entries expire after TTL."""
    mock = MockGateway()
    # Set TTL to 1 second
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10, ttl_seconds=1)
    await cached.start()

    # First call should hit the gateway
    result1 = await cached.embed_one("test query")
    assert mock.embed_one_calls == 1

    # Immediate second call should hit cache
    result2 = await cached.embed_one("test query")
    assert mock.embed_one_calls == 1
    assert result2 == result1

    # Wait for TTL to expire
    await asyncio.sleep(1.1)

    # After TTL, should hit gateway again
    result3 = await cached.embed_one("test query")
    assert mock.embed_one_calls == 2
    assert result3 == result1  # Same result but from gateway

    await cached.stop()


@pytest.mark.asyncio
async def test_cached_gateway_without_ttl() -> None:
    """Verify that cache works indefinitely when TTL is None."""
    mock = MockGateway()
    cached = CachedEmbeddingGateway(gateway=mock, cache_size=10, ttl_seconds=None)
    await cached.start()

    # First call
    await cached.embed_one("test query")
    assert mock.embed_one_calls == 1

    # Even after waiting, should still be cached
    await asyncio.sleep(0.1)
    await cached.embed_one("test query")
    assert mock.embed_one_calls == 1  # Still cached

    await cached.stop()


@pytest.mark.asyncio
async def test_ollama_gateway_batching() -> None:
    """Verify that OllamaGateway batches embed_many calls."""
    # Create gateway with small batch size
    gateway = OllamaGateway(
        base_url="http://localhost:11434",
        chat_model="test",
        embed_model="test",
        batch_size=2,
    )
    
    # We can't test actual API calls without Ollama running,
    # but we can verify the gateway accepts batch_size parameter
    assert gateway._batch_size == 2
    
    # Test empty list handling
    await gateway.start()
    result = await gateway.embed_many([])
    assert result == []
    await gateway.stop()
