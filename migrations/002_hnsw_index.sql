-- Add HNSW index for fast approximate nearest-neighbour search.
-- HNSW offers lower query latency and better recall than ivfflat
-- without requiring training data; ivfflat has been removed in favour of HNSW.

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
