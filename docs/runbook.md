# FinDocBot Runbook

## Prerequisites

- Python 3.12+
- `uv`
- Docker + Docker Compose
- Ollama models available:
  - `qwen2.5:7b`
  - `nomic-embed-text:latest`

## Environment

1. Copy environment template:
   - `cp .env.example .env`
2. Adjust variables if needed:
   - `OLLAMA_BASE_URL`
   - `OLLAMA_CHAT_MODEL`
   - `OLLAMA_EMBED_MODEL`
   - `OLLAMA_NUM_CTX` / `OLLAMA_NUM_PREDICT` — prompt window and answer
     token cap for generation; a prompt longer than the window is silently
     cut from the start, so raise it together with `top_k`.
   - `EMBEDDING_DIM` — output size of the embedding model (768 for
     `nomic-embed-text`); sizes `chunks.embedding` when migrations run, and
     the API refuses to start if the column disagrees.
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
   - `make migrate` (Alembic; runs `alembic upgrade head` against `POSTGRES_DSN`)
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
- Coverage (CI enforces ≥90%):
  - `make cover`
- Integration tests (requires Docker; CI runs them in a separate job):
  - `uv run pytest --integration`
- Full manual E2E pass: see [manual-testing.md](manual-testing.md)

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
