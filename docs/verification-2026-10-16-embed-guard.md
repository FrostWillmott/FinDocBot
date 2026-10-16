# Verification: refusing an embedding input longer than the window (2026-10-16)

**Change.** `OllamaGateway` sends `"truncate": false` on every `/api/embed` request and
maps Ollama's 400 "the input length exceeds the context length" to
`EmbeddingInputTooLongError`. Ingestion stores a fixed client-safe message for it and
logs the cause; the search use case turns it into `InvalidQueryError("Query is too
long.")`, which the route answers with 400.

**Method.** The `verify` skill: throwaway pgvector Postgres, a stub Ollama that logs the
`truncate` field of every `/api/embed` body and refuses (400, Ollama's exact body) any
request whose longest input is over `STUB_MAX_CHARS`, real uvicorn and worker from a
scratch directory (no `.env`). The sample's chunks are 804 to 1,170 characters long.

| Flow | Verdict | Observed |
|------|---------|----------|
| A. Limit not reached: upload, then poll | PASS | 202, then `ready`; 5 chunks |
| A. `/search`, `/ask` | PASS | 200 with 3 hits; 200 |
| A. Embed requests carry `truncate: false` | PASS | 3 of 3 (one ingestion batch, two queries), none without |
| B. Limit 300 characters, every chunk refused: upload, then poll | PASS | 202, then `failed` with "A passage of the document is too long for the embedding model; the server's chunk size or embedding window needs adjusting." |
| B. Chunks stored for the failed document | PASS | 0 |
| B. Short query on the empty index | PASS | 200, 0 hits (a short query is not refused) |
| B. Query of 480 characters | PASS | 400 `{"detail": "Query is too long."}` |
| B. The cause in the server log | PASS | `WARNING findocbot.use_cases.ingestion: Ingestion of document ... failed: An input is longer than 8192 tokens, the embedding window (OLLAMA_EMBED_NUM_CTX)` |

**Found by this check.** The first run of B had no log line: ingestion never logged why
a document failed (a `ModelProviderError` was stored as the generic message, the cause
dropped), although a comment and a decision entry said the setting stayed in the log.
The cause is now logged at WARNING for every `FinDocBotError` that fails a document, with
a test.

**Against the real Ollama** (outside this stubbed run): a 20,000-character input at a
2048 window, `truncate` left at its default, came back `200` with 2047 tokens; with
`truncate: false`, `400 {"error":"the input length exceeds the context length"}`, also for
a batch that holds one long input and one short. The e2e job runs the two new tests
(`test_upload_chunk_over_the_embedding_window_fails_the_document`,
`test_search_query_over_the_embedding_window_responds_400`) against the `0.35.1` image.

**Measured, real reports, `CHUNK_TOKENS=300`, the embedder's own tokenizer** (per-chunk
`prompt_eval_count`):

| Report | Chunks | Median | p99 | Longest | Over 2048 | Over 8192 |
|--------|--------|--------|-----|---------|-----------|-----------|
| English | 547 | 303 | 608 | 656 | 0 | 0 |
| Russian | 130 | 692 | 885 | 926 | 0 | 0 |
| Armenian | 59 | 1,582 | 2,267 | 2,322 | 6 | 0 |
