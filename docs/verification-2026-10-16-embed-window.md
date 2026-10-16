# Verification: explicit embedding window (2026-10-16)

**Change.** `OllamaGateway` sends `"options": {"num_ctx": N}` on every `/api/embed`
request, with `N` from the new setting `OLLAMA_EMBED_NUM_CTX` (default 8192). Before,
Ollama loaded `qwen3-embedding:0.6b` at its own maximum of 32768 tokens.

**Method.** The `verify` skill: throwaway pgvector Postgres, stub Ollama that logs the
model and `options` of each `/api/embed` body, real uvicorn and worker from a scratch
directory (no `.env`, default `Settings`). Then the production gateway against the real
local Ollama, reading the loaded size from `ollama ps`.

| Flow | Verdict | Observed |
|------|---------|----------|
| Upload the sample PDF, then poll | PASS | 202, then `ready` |
| `POST /ask`, and a follow-up with the returned `session_id` | PASS | 200 and 200; 1 and 2 generate calls |
| Embed requests seen by the stub | PASS | 3 (one ingestion batch, two query embeddings), all model `qwen3-embedding:0.6b`, options `{"num_ctx": 8192}` |
| Real Ollama, `embed_many` through the gateway with default `Settings` | PASS | two 1024-dimension vectors; `qwen3-embedding:0.6b` loaded at **2.9 GB** |
| Same model on the real Ollama without the option (measured earlier, direct request) | for comparison | 5.8 GB at a 32768 window; 2.2 GB at 2048 |

The generate calls in the stubbed run carry `qwen2.5:7b` and no `think` field because
this branch is cut from `master`, which does not have the chat-model change yet; that
belongs to its own change.

The stub returns constant vectors, so this shows the plumbing and the memory, not
retrieval quality. Nothing here measures whether any real chunk exceeds the window: Ollama
cuts a longer input silently, and the token count of Russian and Armenian chunks was not
measured (see `DECISIONS.md`).
