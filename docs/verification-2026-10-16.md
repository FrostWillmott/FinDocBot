# Verification: qwen3-embedding default and revision 0006 (2026-10-16)

**Change.** `Settings` defaults to `qwen3-embedding:0.6b` and `EMBEDDING_DIM=1024`
(was `nomic-embed-text`, 768). Alembic revision 0006 resizes `chunks.embedding` to
`EMBEDDING_DIM` (falling back to the `Settings` default); when the column already has
that size it does nothing, otherwise it deletes the chunks and marks every document
that is not already `failed` as failed with "The embedding model changed; upload the
document again.".

**Method.** The `verify` skill: throwaway pgvector Postgres, a stub Ollama (the
embedding size is a parameter; `/api/generate` returns a fixed reply), real uvicorn and
worker started from a scratch directory so the repository's `.env` is not read. The
stub logs the model name it is asked to embed with. One database, reset between
scenarios; Alembic run through the real CLI.

| Flow | Verdict | Observed |
|------|---------|----------|
| A. Fresh database, `EMBEDDING_DIM` unset, `alembic upgrade head` | PASS | column `vector(1024)`, revision `0006` |
| A. App with default `Settings` starts, upload, poll | PASS | 202, then `ready`; 5 chunks; the stub saw only `qwen3-embedding:0.6b` |
| A. `/search`, `/ask` | PASS | 3 hits; answer `high`, 2 sources |
| B. Database at revision 0005 with a 768 column and one `ready` document (app run with `nomic-embed-text`, 768) | PASS | column `vector(768)`; 5 chunks |
| D. Default `Settings` (1024) against that 768 column | PASS | process exits at startup: "chunks.embedding is vector(768) but EMBEDDING_DIM is 1024; re-run migrations or fix the setting." |
| C. `EMBEDDING_DIM=1024 alembic upgrade head` on that database | PASS | column `vector(1024)`, revision `0006`, 0 chunks, document `failed` with the model-changed message |
| C. App starts; `GET /documents`; `/search` before re-upload | PASS | the failed document and its message are listed; 0 hits |
| C. Upload the same PDF again | PASS | 202, same `document_id`, polls to `ready`; 5 chunks, 1 document |
| C. `/search` after the re-upload | PASS | 3 hits |
| Column already the target size (upgrade is a no-op) | SKIP | not repeated here; covered by `tests/integration/test_migrations.py` (`test_upgrade_with_matching_dimension_*`) |
| Downgrade to 0005 | SKIP | covered by `test_downgrade_from_1024_restores_the_768_column` |

## Captured output

```text
=== A. fresh database, EMBEDDING_DIM unset, default Settings
column: vector(1024)  revision: 0006
app up
upload: 202
poll: ready None
chunks: 5
search: 3 hits
ask: Total revenue was USD 1,284 million. high 2
embed models the app asked for: qwen3-embedding:0.6b
=== B. existing 768 database
column: vector(768)  revision: 0005
app up (nomic, 768)
upload: 202
poll: ready None
chunks before: 5  docs: ready
=== D. default Settings (1024) against the 768 column
api up: no  process alive: no
findocbot.domain.exceptions.EmbeddingDimensionError: chunks.embedding is vector(768) but EMBEDDING_DIM is 1024; re-run migrations or fix the setting.
=== C. migrate the 768 database to head with EMBEDDING_DIM=1024
column: vector(1024)  revision: 0006
chunks after: 0
document: failed | The embedding model changed; upload the document again.
app up (defaults, 1024)
listed: [('failed', 'The embedding model changed; upload the document again.')]
search before re-upload: 0 hits
re-upload: 202 same id: yes
poll: ready None
chunks: 5  documents: 1
search after re-upload: 3 hits
```

The stub returns constant vectors, so this shows the plumbing, not retrieval quality;
the real-Ollama check is `pytest --e2e -m e2e` and the quality figures are in
`evals/results/2026-10-16-embedders/`.

Not exercised here: a developer `.env` that still says `OLLAMA_EMBED_MODEL=nomic-embed-text:latest` and
`EMBEDDING_DIM=768` keeps working (revision 0006 changes nothing); it only moves to the
new model when both lines are updated, see "Changing the embedding model" in
`docs/runbook.md`.
