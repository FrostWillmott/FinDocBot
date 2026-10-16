# FinDocBot Runbook

## Prerequisites

- Python 3.12+
- `uv`
- Docker + Docker Compose
- Ollama models available:
  - `qwen2.5:7b`
  - `qwen3-embedding:0.6b`

## Environment

1. Copy environment template:
   - `cp .env.example .env`
2. Adjust variables if needed:
   - `OLLAMA_BASE_URL`
   - `OLLAMA_CHAT_MODEL`
   - `OLLAMA_EMBED_MODEL`
   - `OLLAMA_RERANK_MODEL` — optional reranker (empty = off). When set,
     `/search` and `/ask` fetch `RERANK_CANDIDATES` (20) candidates by vector
     search, rerank them and keep the best `top_k`; the reported `score` is then
     the reranker's, not the cosine similarity. If the reranker fails or takes
     longer than `RERANK_TIMEOUT_SECONDS` (30), search keeps the vector order
     and logs a warning. It costs about 0.4 s per candidate on an M1 Pro, so
     run Ollama natively, not in the CPU-only container, and see
     `evals/README.md` before turning it on.
   - `OLLAMA_NUM_CTX` / `OLLAMA_NUM_PREDICT` — prompt window and answer
     token cap for generation; a prompt longer than the window is silently
     cut from the start, so raise it together with `top_k`.
   - `EMBEDDING_DIM` — output size of the embedding model (1024 for
     `qwen3-embedding:0.6b`); sizes `chunks.embedding` when migrations run,
     and the API refuses to start if the column disagrees (see
     "Changing the embedding model" below).
   - `POSTGRES_DSN`
   - `OLLAMA_TIMEOUT_SECONDS` — per-request timeout to Ollama (120 s).
   - `DB_POOL_MAX_SIZE` — PostgreSQL connection pool size (5).
   - `CHUNK_TOKENS` / `CHUNK_OVERLAP_RATIO` — chunk size and overlap for new
     uploads (300 / 0.15); documents already indexed keep their chunks.
     Raise `OLLAMA_NUM_CTX` along with `CHUNK_TOKENS`.
   - `LOG_LEVEL` — level for the app's own loggers (`INFO` by default);
     libraries stay at `WARNING`.

## Local Development (without Docker API)

1. Install dependencies:
   - `make sync`
2. Start infrastructure only (`make up` would also start the `api`
   container on port 8000):
   - `docker compose up -d db ollama`
3. Apply migrations:
   - `make migrate` (Alembic; runs `alembic upgrade head` against `POSTGRES_DSN` from the environment or `.env`)
4. Run API locally:
   - `make dev`
5. Health check:
   - `curl http://localhost:8000/health` — 200 when PostgreSQL and Ollama
     both answer, 503 with the failing check marked `unavailable` otherwise.

## Full Docker Run

1. Build and start all services:
   - `make up`
2. View logs:
   - `make logs`
3. Stop services:
   - `make down`

## Quality Checks

- Lint and format check:
  - `make lint`
- Auto-fix formatting/lint:
  - `make fmt`
- Static type checking:
  - `uv run mypy src/findocbot`
- Tests:
  - `make test`
- Coverage over unit and integration tests together (requires Docker; CI enforces the
  `fail_under` threshold in `pyproject.toml`):
  - `make cover`
- Integration tests alone (requires Docker):
  - `uv run pytest --integration -m integration`
- End-to-end tests (requires Docker; starts Postgres and Ollama and pulls ~1 GB of models; CI runs them in a separate job):
  - `make e2e`
- Full manual E2E pass: see [manual-testing.md](manual-testing.md)

## Changing the embedding model

Vectors from different models are not comparable and pgvector cannot cast
between sizes, so the model and `chunks.embedding` change together.

- **Fresh database**: set `OLLAMA_EMBED_MODEL` and `EMBEDDING_DIM` before the
  first `make up` / `make migrate`; the column is created at that size.
- **Existing database on `nomic-embed-text` (768)**: pull the new model, set
  `OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b` and `EMBEDDING_DIM=1024` (or drop
  both lines to take the defaults), then run `make migrate` (or `make up`).
  Revision 0006 deletes every chunk, resizes the column and marks each
  document `failed` with "The embedding model changed; upload the document
  again." Upload each PDF again: a failed document is retried, not
  deduplicated. Take a `pg_dump` first if the chunk text matters, since it is
  not kept.
- **Staying on 768**: keep `EMBEDDING_DIM=768` and the old model; revision 0006
  then changes nothing.
- **Any later change of size** needs a new revision: Alembic applies 0006 once,
  so editing `EMBEDDING_DIM` afterwards only makes the API refuse to start.

## Pre-commit

Hooks: `ruff check`, `ruff format`, `mypy` (strict), `pytest`.

1. Install pre-commit hooks:
   - `make precommit-install`
2. Run hooks manually:
   - `uv run pre-commit run --all-files`

## API Quick Smoke

1. Upload PDF:
   - `POST /documents/upload` with `multipart/form-data` field `file`.
     Returns `202 Accepted` with `document_id` and `status: "pending"`.
   - Poll `GET /documents/{document_id}` until `status` is `ready` (or
     `failed` with an `error`).
2. Search:
   - `POST /search` with payload:
     - `{"query":"revenue in q4","top_k":3}`
3. Ask:
   - `POST /ask` with payload:
     - `{"question":"How did revenue change?","top_k":3}` — the response
       carries a `session_id`; send it back to continue the dialogue.

## Troubleshooting

- If API cannot connect to DB:
  - ensure `db` container is healthy: `docker compose ps`
- If model calls fail:
  - verify Ollama service is running and models are pulled.
- If pgvector is missing:
  - ensure image is `pgvector/pgvector:pg16`.
