# Verification: ingestion module refactor (2026-10-15)

**Change.** `UploadPDFUseCase` + `InProcessUploadQueue` + `UploadQueuePort` became
`IngestionUseCase` with a private queue. Behaviour is meant to be unchanged.

**Method.** The `verify` skill: throwaway pgvector Postgres, stub Ollama (768-dim
embeddings, fixed `/api/generate` reply), the same driver script against the
pre-refactor commit (`f3be3ce`, via `git worktree` and `--app-dir`) and against the
working tree. Output compared line by line.

| Flow | Verdict | Observed (identical before and after) |
|------|---------|---------------------------------------|
| `GET /health` | PASS | 200 |
| Upload a new PDF, then poll | PASS | 202 `pending`; polls to `ready`, `error` null |
| Re-upload the same bytes after `ready` | PASS | 200, same `document_id`, status `ready` |
| Upload bytes that are not a PDF, then poll | PASS | 202 `pending`; polls to `failed`: "Uploaded file is not a readable PDF: Stream has ended unexpectedly" |
| `POST /search` | PASS | 200, 3 chunks |
| `POST /ask` | PASS | 200, stub answer, `high`, 2 sources |
| `GET /documents` | PASS | 200, statuses `['failed', 'ready']` |
| SIGINT shutdown (worker stopped by the lifespan) | PASS | "Application shutdown complete", no traceback, in both runs |
| Duplicate of a still-pending upload | SKIP | Not observable with a stub that answers instantly; pinned in `tests/e2e/test_routes.py` (issue #39) |
| Unexpected error during ingestion | SKIP | Needs a provider that raises a non-domain error; pinned in `tests/e2e/test_routes.py` (issue #36) |

## Captured output

Identical for the baseline and the working tree:

```text
health 200
upload new 202 pending
poll ready None aurora.pdf
upload dup after ready 200 ready True
upload garbage 202 pending
poll garbage failed Uploaded file is not a readable PDF: Stream has ended unexpectedly
search 200 3
ask 200 Total revenue was USD 1,284 million. high 2
list 200 ['failed', 'ready']
```

The real-Ollama check is `pytest --e2e -m e2e`; this report covers the stubbed run only.
