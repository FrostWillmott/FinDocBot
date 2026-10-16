# Verification 2026-10-16: a chunk fits the source cap at any CHUNK_TOKENS

Change: `ParagraphTokenChunker`'s default ceiling is
`min(chunk_tokens x 10, MAX_SOURCE_CHARS)` and logs one WARNING when the second
term wins; the answer prompt, the reranker prompt and the chunker share
`MAX_SOURCE_CHARS` / `MAX_QUESTION_CHARS` from `use_cases/prompt_safety.py`.

Setup: throwaway `pgvector/pgvector:pg16` on :55432 (one database per app),
Alembic migrations applied, stub Ollama on :51434 (1024-dim embeddings),
`CHUNK_TOKENS=500`. The PDF is 1,500 copies of "internationalization" (20
characters each, so 500 chunker tokens are about 10,000 characters). Before = a
worktree of `4e1767a` (`--app-dir`); after = this branch.

| Flow | Before | After | Verdict |
|------|--------|-------|---------|
| `POST /documents/upload`, poll until done | `ready`, 10 chunks | `ready`, 11 chunks | PASS |
| `POST /search` (`top_k=20`), longest chunk text | 4,980 characters (the answer prompt would cut it at 4,000) | 3,920 characters | PASS |
| Startup log | no warning | one WARNING: `chunk_tokens=500 allows 5000 characters per chunk; capped at 4000, the longest source the answer prompt carries` | PASS |

At the default `CHUNK_TOKENS=300` nothing changes and nothing is logged
(unit test `test_init_default_chunk_tokens_logs_no_warning`). Stack torn down
afterwards.
