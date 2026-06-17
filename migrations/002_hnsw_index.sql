-- Add HNSW index for faster approximate nearest-neighbour search.
-- HNSW offers lower query latency than ivfflat at the cost of higher
-- build time and memory usage.  Both indexes coexist; the query planner
-- picks the cheaper one (HNSW wins for small top_k / low-concurrency).

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
