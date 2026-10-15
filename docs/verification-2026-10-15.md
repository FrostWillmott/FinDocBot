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
| Duplicate of a still-pending upload | PASS | See "Duplicate of a pending upload (#39)" below |
| Unexpected error during ingestion | PASS | See "Unexpected error during ingestion (#36)" below |

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

## Unexpected error during ingestion (#36)

**Change.** `IngestionUseCase` marks a document `failed` with the fixed text
`Ingestion failed unexpectedly.` when ingestion raises an error it did not
anticipate; before, the document stayed `pending` for ever.

**Method.** Real uvicorn, real worker, throwaway Postgres, the same stub Ollama. A
launcher (`verify_app`) wraps the real app factory with one injected fault: the PDF
parser raises `RuntimeError("secret internal detail ...")` for bytes starting with
`BOOM`, standing in for a pypdf bug outside the mapped list. The stub cannot provoke
a non-domain error by itself: a wrong embedding count is a `ModelProviderError`, and
stopping Postgres would also stop the status update from being recorded. The same
driver ran against the commit before the fix (`274beb4`) and the working tree.

| Flow | Before | After |
|------|--------|-------|
| Upload the faulty bytes | 202 `pending` | 202 `pending` |
| Upload the sample PDF right after | `ready` | `ready` (the worker kept going) |
| Poll the faulty document | `pending`, `error` null | `failed`, `error` "Ingestion failed unexpectedly." |
| Responses containing "secret internal detail" | 0 | 0 |
| Server log | "Upload worker failed on job ..." with traceback | "Unexpected error ingesting document ..." with traceback |

**Verdict: PASS.** The regular flow above, rerun on the fix, printed the same output
as before.

## Duplicate of a pending upload (#39)

**Change.** `IngestionUseCase.submit` returns a `Submission` saying whether it queued
ingestion; the route answers 202 only when it did, so a duplicate of a pending upload
now gets 200, as `README.md` and `DECISIONS.md` say. Before, the route read
`document.status` and answered 202.

**Method.** The stub Ollama delays `/api/embed` by 3 seconds so the document stays
`pending` long enough to upload the same bytes again. The same driver ran against the
commit before the fix (`473d12c`) and the working tree, on a fresh database each.

| Step | Before | After |
|------|--------|-------|
| First upload | 202 `pending` | 202 `pending` |
| Same bytes while `pending` | **202** `pending`, same `document_id` | **200** `pending`, same `document_id` |
| Document settles | `ready` | `ready` |
| Same bytes after `ready` | 200 `ready`, same `document_id` | 200 `ready`, same `document_id` |
| Documents listed / chunks stored | 1 / 5 | 1 / 5 |

**Verdict: PASS.** The regular flow above, rerun on the fix, printed the same output as
before.

## Search only returns chunks of ready documents (#40)

**Change.** `PostgresChunkRepository.search_by_embedding` joins `documents` and keeps
rows whose status is `ready`. Before, any stored chunk was searchable, including those
of a `pending` or `failed` document.

**Method.** Real uvicorn, worker and Postgres, the stub Ollama. After a sample PDF
reached `ready`, its status was forced with SQL (`pending`, `failed`, `ready`) to stand
in for the window where chunks are committed but the status update has not happened or
failed. `/search` and `/ask` ran at each status, against the commit before the fix
(`4ac2933`) and the working tree.

| Document status | `/search` hits / `/ask` sources before | after |
|-----------------|----------------------------------------|-------|
| `ready` | 5 / 5 | 5 / 5 |
| forced `pending` | 5 / 5 | **0 / 0** |
| forced `failed` | 5 / 5 | **0 / 0** |
| `ready` again | 5 / 5 | 5 / 5 |

**Query plan.** On 10,000 random 768-dimension chunks, 10% of them in `pending`
documents, `EXPLAIN ANALYZE` of the joined query still shows
`Index Scan using idx_chunks_embedding_hnsw` (a nested loop with a memoized primary-key
lookup on `documents`), and `LIMIT 5` and `LIMIT 20` both return the full row count.

**Verdict: PASS.**
