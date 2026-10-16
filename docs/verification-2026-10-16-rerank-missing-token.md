# Verification 2026-10-16: reranker reply without a readable yes/no

Change: `OllamaReranker` scores with one shared `yes_probability` (a missing
yes/no token counts as log-probability -10) and treats a malformed
`top_logprobs` entry as a `ModelProviderError`.

Setup: throwaway `pgvector/pgvector:pg16` on :55432 with the Alembic migrations
applied, a stub Ollama on :51434 (1024-dim embeddings; `/api/generate` with
`logprobs` returns a scripted `top_logprobs`), `OLLAMA_RERANK_MODEL` set, the
sample report uploaded until `ready`. Before = a worktree of `ae88b45`
(`--app-dir`, confirmed by the traceback paths); after = this branch.

| Flow | Reranker reply | Before | After | Verdict |
|------|----------------|--------|-------|---------|
| `POST /search` | first token `maybe` (neither word) | 500, `ZeroDivisionError` | 200, results | PASS |
| `POST /search` | entry without `token` | 500, `KeyError: 'token'` | 200, vector order; log `Reranking failed, keeping vector order: ModelProviderError('Ollama reply has no usable logprobs; ...')` | PASS |
| `POST /search` | `yes` -0.1, `no` -2.3 | not run | 200, scores `[0.9, 0.9]` (e^-0.1 / (e^-0.1 + e^-2.3) = 0.9) | PASS |

`/ask` shares the search path (`SearchSimilarChunksUseCase`) and was not run
separately. Stack torn down afterwards.
