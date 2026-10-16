# Verification 2026-10-16: `Document.create` requires a status

Change: `status` is a required keyword on `Document.create`; the only
production caller (`IngestionUseCase.submit`) already passed `"pending"`.

Setup: throwaway `pgvector/pgvector:pg16` on :55432 with the Alembic
migrations applied, a stub Ollama on :51434 (1024-dim embeddings), the app on
:58000.

| Flow | Result | Verdict |
|------|--------|---------|
| `POST /documents/upload` of the sample report | 202, `status: "pending"` | PASS |
| `GET /documents` after the worker ran | `status: "ready"`, `error: null` | PASS |
| `POST /search` (`top_k=3`) | 3 results | PASS |
| `POST /documents/upload` of the same bytes | 200 (duplicate) | PASS |
| App log | no traceback | PASS |

The repository behaviour of this branch (the shared contract suite) is covered
by the unit and integration tests, not by this check. Stack torn down afterwards.
