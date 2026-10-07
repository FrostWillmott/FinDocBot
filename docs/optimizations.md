# Embedding and vector-search optimizations

FinDocBot keeps its embedding path lean in a few ways: `OllamaGateway` reuses
a single `httpx.AsyncClient` for its lifetime instead of opening a connection
per request; `CachedEmbeddingGateway` caches query embeddings in a TTL-bounded
LRU cache (document chunks are not cached, since they are unique); and
`embed_many` batches large documents into fixed-size chunks so a many-page PDF
does not trip a single oversized request. These changes are correctness and
robustness improvements rather than measured wins — no benchmarks have been
run, so no latency or throughput numbers are claimed here.
