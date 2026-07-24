# Decisions

Append-only log of non-obvious technical decisions a future contributor would
otherwise re-litigate. Each entry: date — decision — reason. If a decision is
later reversed, add a superseding entry instead of editing the old one.

## Founding decisions (recorded retroactively on 2026-07-24)

- **Local LLM via Ollama instead of a hosted API** — data privacy for
  financial documents and zero per-call cost; the provider sits behind a
  `ModelProviderGateway` port, so swapping to a hosted API is a one-module
  change.
- **PostgreSQL + pgvector with an HNSW index** (`m=16, ef_construction=64`,
  cosine ops) — one database for relational data and vectors; HNSW chosen over
  IVFFlat for higher recall and no `ANALYZE`-after-population requirement.
- **Full Clean Architecture split** (domain / use cases / adapters /
  infrastructure) — deliberate learning exercise: this project is a testbed
  for technologies and patterns not available at the day job, and the goal
  was to live with the full split long enough to see where it pays off and
  where it is ceremony. The lighter 3-layer split would suffice for this
  size otherwise.
- **Document row is persisted only after embeddings succeed**, and rolled back
  if chunk insertion fails — avoids orphan documents without requiring a
  cross-service distributed transaction.

## 2026-07-24

- **Coverage enforced in CI at ≥80% on the unit-test run** — threshold gives
  headroom below the current ~92% so a small refactor doesn't break the build.
  Integration tests run in a separate CI job (fast unit feedback; Docker pulls
  isolated), so their coverage does not count toward the threshold.
- **Static coverage badge (shields.io) instead of Codecov** — no external
  service or token for a small personal project; the number is updated
  manually when it moves materially.
- **English is the documentation language** for README and `docs/` —
  international-team standard.
