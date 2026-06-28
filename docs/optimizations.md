# Embedding Processing and Vector Search Optimizations

## Overview

This document describes the implemented optimizations to improve embedding processing performance and vector search in FinDocBot.

## Implemented Optimizations

### 1. HTTP Client Reuse in OllamaGateway

**Problem:** Each request to the Ollama API created a new `httpx.AsyncClient`, leading to connection setup overhead.

**Solution:** Added `start()` and `stop()` lifecycle methods to manage a single HTTP client throughout the application's lifecycle.

**File:** `src/findocbot/infrastructure/ollama_gateway.py`

**Changes:**
- Added `_client: httpx.AsyncClient | None` field.
- `start()` method initializes the client.
- `stop()` method correctly closes connections.
- `embed_one()`, `embed_many()`, and `generate()` methods use the reusable client.

**Benefits:**
- Latency reduction by reusing TCP connections.
- Reduced overhead for creating/destroying clients.
- More efficient use of connection pooling.

### 2. LRU Caching of Request Embeddings with TTL and Metrics

**Problem:** Repeating user queries recomputed embeddings, which is inefficient. There were no metrics to monitor cache effectiveness in production.

**Solution:** Created `CachedEmbeddingGateway` — a wrapper with LRU cache, TTL, and metrics for user query embeddings.

**File:** `src/findocbot/infrastructure/cached_embedding_gateway.py`

**Architecture:**
- Uses `OrderedDict` to implement LRU logic.
- Caches only `embed_one()` (user queries).
- Does NOT cache `embed_many()` (document chunks — typically unique).
- Cache key: SHA256 hash of the query text.
- Stores a timestamp for each entry to support TTL.

**New Features:**

1. **Cache Metrics:**
   - Hits/misses counters to track effectiveness.
   - `get_stats()` method returns `CacheStats` with metrics.
   - Automatic statistics logging on shutdown.
   - Hit rate for assessing caching efficiency.

2. **TTL (Time To Live):**
   - Optional `ttl_seconds` parameter for automatic entry expiration.
   - TTL check on every cache access.
   - Automatic removal of stale entries.
   - Default: 3600 seconds (1 hour).

3. **Large Size Warning:**
   - Automatic warning if `cache_size > 10000`.
   - Helps avoid excessive memory consumption.

**Configuration:**
- `embedding_cache_size` in `Settings` (default: 1000).
- `embedding_cache_ttl_seconds` in `Settings` (default: 3600).
- Configurable via environment variables or code.

**Benefits:**
- Instant response for repeating queries.
- Reduced load on the Ollama API.
- Saving computational resources.
- Production-ready metrics for monitoring.
- Automatic cleanup of stale data.

**Usage Example:**
```python
# In container.py
ollama_gateway = OllamaGateway(...)
provider = CachedEmbeddingGateway(
    gateway=ollama_gateway,
    cache_size=settings.embedding_cache_size,
    ttl_seconds=settings.embedding_cache_ttl_seconds,
)

# Getting metrics
stats = provider.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Cache size: {stats.size}/{stats.max_size}")
```

### 3. Automatic Embedding Batching in Gateway

**Problem:** Large documents with hundreds of chunks sent all embeddings in a single request, which could cause timeouts or API overload. Batching in the use case violated Clean Architecture principles — the use case should not know about implementation details.

**Solution:** Batching moved from `UploadPDFUseCase` to `OllamaGateway`, where it is an implementation detail invisible to use cases.

**File:** `src/findocbot/infrastructure/ollama_gateway.py`

**Changes:**
- Added `batch_size` parameter to `OllamaGateway` constructor (default: 50).
- `embed_many()` method automatically splits large lists into batches.
- Batch results are transparently merged into a single list.
- Use cases simply call `embed_many()` without knowing about batching.

**Configuration:**
- `embedding_batch_size` in `Settings` (default: 50).
- Passed to `OllamaGateway` via `container.py`.

**Benefits:**
- Preventing timeouts on large documents.
- More stable API interaction.
- Ability to process documents of any size.
- **Adherence to Clean Architecture principles** — the use case doesn't know about implementation details.
- Transparency for all use cases.

**Code Example:**
```python
# In OllamaGateway.embed_many()
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
            json={"model": self._embed_model, "input": batch},
        )
        response.raise_for_status()
        payload = response.json()
        all_embeddings.extend(payload["embeddings"])
    
    return all_embeddings

# Use case is now simply:
embeddings = await self._provider.embed_many([c.text for c in built_chunks])
```

### 4. Lifecycle Management in AppContainer

**Problem:** Lack of centralized lifecycle management for components with external resources.

**Solution:** Updated `AppContainer` to manage the provider's lifecycle.

**File:** `src/findocbot/infrastructure/container.py`

**Changes:**
- Added `provider: CachedEmbeddingGateway` field to the container.
- `startup()` method calls `provider.start()`.
- `shutdown()` method calls `provider.stop()` for correct cleanup.

**Benefits:**
- Guaranteed resource initialization on start.
- Correct resource release on stop.
- Centralized lifecycle management.

## Configuration

New parameters in `src/findocbot/config.py`:

```python
@dataclass(frozen=True)
class Settings:
    # ... existing parameters ...
    embedding_cache_size: int = 1000                    # LRU cache size for embeddings
    embedding_batch_size: int = 50                      # Batch size for document uploads
    embedding_cache_ttl_seconds: int | None = 3600      # Cache entry TTL (1 hour)
```

Override via environment variables:
```bash
export EMBEDDING_CACHE_SIZE=2000
export EMBEDDING_BATCH_SIZE=100
export EMBEDDING_CACHE_TTL_SECONDS=7200  # 2 hours
```

## Testing

Comprehensive tests created in `tests/test_embedding_cache.py`:

1. **test_cached_gateway_caches_identical_queries** — verification of identical query caching.
2. **test_cached_gateway_does_not_cache_embed_many** — verification of no cache for batch operations.
3. **test_cached_gateway_respects_cache_size** — verification of cache size and LRU logic compliance.
4. **test_cached_gateway_clears_cache_on_stop** — verification of cache clearing on stop.
5. **test_cached_gateway_tracks_metrics** — verification of hit/miss and hit rate metric correctness.
6. **test_cached_gateway_respects_ttl** — verification of TTL expiration.
7. **test_cached_gateway_without_ttl** — verification of operation without TTL (infinite storage).
8. **test_ollama_gateway_batching** — verification of batching in OllamaGateway.

All tests pass successfully.

## Performance Metrics

### Expected Improvements:

1. **Repeating Queries:**
   - Without cache: ~200-500ms (Ollama API call).
   - With cache: <1ms (memory read).
   - **Acceleration: 200-500x.**

2. **Large Document Upload:**
   - Without batching: risk of timeout on >100 chunks.
   - With batching: stable processing of any size.
   - **Reliability: significantly improved.**

3. **HTTP Connections:**
   - Without reuse: new connection per request.
   - With reuse: single connection.
   - **Latency reduction: 10-50ms per request.**

## Monitoring

The cache provides built-in metrics for production monitoring:

```python
# Getting cache metrics
stats = provider.get_stats()

print(f"Cache hits: {stats.hits}")
print(f"Cache misses: {stats.misses}")
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Current size: {stats.size}/{stats.max_size}")

# Metrics are automatically logged on shutdown:
# INFO: Cache stats: 150 hits, 50 misses, hit rate: 75.00%, final size: 45
```

**Prometheus Integration (Future Improvement):**
```python
from prometheus_client import Counter, Gauge

cache_hits = Counter('embedding_cache_hits_total', 'Total cache hits')
cache_misses = Counter('embedding_cache_misses_total', 'Total cache misses')
cache_size = Gauge('embedding_cache_size', 'Current cache size')
```

## Further Optimizations

Possible directions for future improvements:

1. **Vector Search Result Caching** — caching search results, not just embeddings.
2. **Cache Pre-warming** — loading popular queries on start.
3. **Persistent Cache** — saving cache to disk for reuse between restarts.
4. **Prometheus Metrics** — integration with Prometheus for centralized monitoring.
5. **Adaptive Batch Size** — dynamic batch size adjustment based on load.
6. **Distributed Cache** — using Redis for shared cache between instances.

## Compatibility

All optimizations:
- ✅ Backward compatible with the existing API.
- ✅ Require no changes in client code.
- ✅ Transparent for use cases.
- ✅ Follow Ports and Adapters architecture.
- ✅ Covered by tests.

## Conclusion

The implemented optimizations significantly improve system performance when working with embeddings and vector search, while maintaining architectural cleanliness and backward compatibility.
