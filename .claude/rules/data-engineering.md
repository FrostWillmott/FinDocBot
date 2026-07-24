# Data engineering conventions

Apply to pipeline / ETL / data-processing projects. Assumes `python-core.md`.

## Pipelines
- Idempotent stages: re-running a stage on the same input produces the same
  output and doesn't double-write. Design for safe retries.
- Make each stage's inputs and outputs explicit (paths, tables, schemas). No
  hidden global state between stages.
- Validate data at ingestion boundaries (schema, types, null/range checks)
  rather than letting bad data propagate downstream. Pydantic or an explicit
  schema (e.g. pandera/pyarrow schema) at the edge.
- Separate orchestration (what runs when) from transformation logic (pure,
  testable functions). Transformation functions should be unit-testable without
  the orchestrator.

## SQL
- Parameterized queries only — never string-format values into SQL.
- Use the ORM for CRUD; drop to raw SQL for complex analytical queries, and keep
  that raw SQL in named, reviewed places, not scattered inline.
- Be explicit about transactions and batch sizes for large writes.
- Watch for N+1 access patterns; load in bulk.

## Data handling
- Stream or chunk large datasets; don't load more into memory than necessary.
- Make column types and units explicit; don't rely on inference for anything
  that feeds a downstream decision.
- Use `Decimal` for money, never float.
- Keep timezones explicit (store UTC; convert at the edges).

## Reproducibility
- Pin data-tool versions in the lockfile.
- Seed any randomness used in sampling/splits and record the seed.
- Log row counts and key stats at stage boundaries so silent data loss is visible.
