# PostgreSQL & pgvector conventions

Apply to projects using pgvector for vector similarity search. Assumes `python-core.md`.
Rule levels are defined in `_LEVELS.md`.

## Schema  [MUST]
- Use the `pgvector` extension (`CREATE EXTENSION IF NOT EXISTS vector`).
- Define vector columns with `Vector(dim)` where `dim` comes from the embedding
  model's config, never hardcoded as a magic number. A mismatch between the
  stored index and the model silently corrupts search results, not an error.
- Use `Mapped` and `mapped_column` for SQLAlchemy 2.0+ models.

## Indexing  [MUST-UNLESS]
Build an ANN index before running similarity queries on more than a few thousand
rows — without one every query is a full table scan.

- **HNSW** is the default for production: high recall, fast queries, higher RAM.
  ```python
  Index("idx_embedding", Model.embedding,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"})
  ```
  `m=16, ef_construction=64` are reasonable starting points; tune under load.
- **IVFFlat** — lower RAM, slower to build, needs `ANALYZE` after population.
  Use only when HNSW RAM requirements are prohibitive.
- The distance operator in the index (`vector_cosine_ops`, `vector_l2_ops`,
  `vector_ip_ops`) must match the operator used in queries — a mismatch causes
  a silent full scan.

## Distance metrics  [MUST]
Match the metric to how the model was trained:
- `<=>` cosine distance — semantic similarity (most embedding models).
- `<->` L2 / Euclidean — spatial distance.
- `<#>` inner product — only when vectors are pre-normalized.

Always paginate results and set a hard `limit()` — unbounded neighbor queries
are a latency and memory hazard.

## Queries  [MUST]
- Parameterized queries only — never format values into SQL strings.
- Keep vector distance logic in the infrastructure/repository layer. Domain and
  use-case layers work with entities and IDs, not raw distance scores or arrays.
- In a 3-layer setup (no full Clean Architecture), keep distance queries in a
  dedicated repository module, not scattered across services.

## Validation  [MUST]
- Check embedding dimensions match the column before insertion — a silent
  mismatch produces wrong results without raising an exception.
- Verify the `vector` extension is enabled before running migrations.
- Confirm the query operator matches the index operator; a mismatch causes a
  full sequential scan with no warning.
