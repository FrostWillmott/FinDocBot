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
   - `POSTGRES_DSN`

## Local Development (without Docker API)

1. Install dependencies:
   - `make sync`
2. Start infrastructure:
   - `make up`
3. Run API locally:
   - `make dev`
4. Health check:
   - `curl http://localhost:8000/health`

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
- Tests:
  - `make test`

## Pre-commit

1. Install pre-commit hooks:
   - `make precommit-install`
2. Run hooks manually:
   - `uv run pre-commit run --all-files`

## API Quick Smoke

1. Upload PDF:
   - `POST /documents/upload` with `multipart/form-data` field `file`.
2. Search:
   - `POST /search` with payload:
     - `{"query":"revenue in q4","top_k":3}`
3. Ask:
   - `POST /ask` with payload:
     - `{"session_id":"demo","question":"How did revenue change?","top_k":3}`

## Troubleshooting

- If API cannot connect to DB:
  - ensure `db` container is healthy: `docker compose ps`
- If model calls fail:
  - verify Ollama service is running and models are pulled.
- If pgvector is missing:
  - ensure image is `pgvector/pgvector:pg16`.
