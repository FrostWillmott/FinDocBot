# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands use `uv` via the Makefile:

| Task | Command |
|------|---------|
| Install deps | `make sync` |
| Run API (dev) | `make dev` |
| Lint + format check | `make lint` |
| Auto-fix lint/format | `make fmt` |
| Unit tests | `make test` |
| Unit tests + coverage | `make cover` |
| Integration tests (Docker) | `uv run pytest -q --integration -m integration` |
| Type check | `uv run mypy src/findocbot` |
| Start infra (DB + Ollama) | `make up` |
| Stop infra | `make down` |
| Apply migrations | `make migrate` |
| Install pre-commit hooks | `make precommit-install` |

The CI `test` job runs `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest --cov-fail-under=90`. The `integration` job runs `pytest --integration -m integration` separately. `ruff format` also formats Python code blocks in Markdown, so docs fail the check too; the pre-commit ruff hooks cover Markdown for that reason.

## Architecture

The project follows **Clean Architecture**; dependencies point inward:

```
adapters/api   ─┐
                ├─→  use_cases  →  domain
infrastructure ─┘    (ports.py)
```

`infrastructure` implements the ports declared in `use_cases/ports.py`; use
cases never import it. `main.py` and `infrastructure/container.py` are the
only places that wire concrete classes.

### Dependency injection

`AppContainer` (`infrastructure/container.py`) is the single composition root.
`create_container(settings)` wires concrete implementations into use cases.
Tests pass a container with in-memory fakes; production uses `create_container`.

`main.py:create_app()` accepts an optional `AppContainer` — when `None`, it
builds one from `load_settings()`. The FastAPI lifespan calls
`container.startup()` / `container.shutdown()`.

### Ports & adapters

Use cases declare their dependencies as `Protocol` classes in `use_cases/ports.py`:

| Port | Role |
|------|------|
| `PDFParserPort` | Extract text from PDF bytes |
| `ChunkerPort` | Split text into (chunk, section) tuples |
| `ModelProviderGateway` | Embeddings + structured generation |
| `DocumentRepositoryPort` / `ChunkRepositoryPort` / `ChatHistoryRepositoryPort` | Persistence |
| `UploadQueuePort` | Queue background ingestion jobs |

Each has a real implementation in `infrastructure/`. Repository fakes live in
`tests/in_memory.py`, provider stubs in the tests that use them; neither ships
in the package. `adapters/api/routes.py` depends on the `ApiServices` Protocol,
not on `AppContainer`, so the API layer never imports `infrastructure`.

### Caching layer

`CachedEmbeddingGateway` wraps `ModelProviderGateway` with a hand-rolled LRU
cache with TTL (an `OrderedDict`, no third-party cache library). It caches only
`embed_one` (query embeddings); `embed_many` and generation pass through uncached.

### Key patterns

- **Error mapping**: `adapters/api/routes.py:_map_use_case_errors()` maps domain
  exceptions to HTTP status codes — `ModelProviderError` → 502,
  `InfrastructureError` → 503, `NotFoundError` → 404, `FinDocBotError` → 400.
- **Sessions**: `/ask` without `session_id` starts a session with a
  server-issued `secrets.token_urlsafe(32)` id (table `sessions`); an id not
  in that table is a 404 (`SessionNotFoundError`), checked before any model call.
- **Follow-up retrieval**: when the session has history, `/ask` first asks the
  model to rewrite the question into a standalone search query (one extra
  generation); invalid output falls back to the original question. The answer
  prompt still gets the user's own question.
- **Health**: `/health` runs `AppContainer.health_checks` (`PostgresPool.ping`,
  `OllamaGateway.ping`: one attempt, no retries) and answers 503 if any fails.
- **CPU-bound offloading**: PDF parsing and chunking run via `asyncio.to_thread()`
  to avoid blocking the event loop.
- **Embedding dimension**: `EMBEDDING_DIM` (`Settings.embedding_dim`) sizes
  `chunks.embedding` in the Alembic migrations. Startup verifies the column
  against the setting, and the chunk repository checks every vector's length
  before insert/search.
- **Prompt safety**: untrusted text (chunks, history, question) goes through
  `use_cases/prompt_safety.neutralize` and sits inside tags, with the
  instructions last.
- **Unreadable PDFs**: the parser maps `PyPdfError` and a fixed list of builtins
  pypdf raises from its internals (found by fuzzing, see DECISIONS.md) to
  `InvalidDocumentError` → 400. Extend that list only with types observed
  from pypdf, never to `Exception`.
- **PDF → chunks**: the parser rebuilds paragraph breaks (blank lines) from line
  positions; the chunker treats them as paragraph boundaries and a paragraph
  starting with `Section`/`Chapter` as a section heading that closes the chunk.
- **Background ingestion**: `POST /documents/upload` stores a `pending`
  document and enqueues the bytes on an in-process asyncio queue; a worker
  parses, chunks, embeds and persists them, then flips the status to `ready`
  or `failed` (with a client-safe `error`). A SHA-256 of the uploaded bytes
  (`documents.content_hash`, unique) makes a re-upload return the stored
  document instead of queueing a second copy.

### Migrations

Alembic, with raw-SQL revisions in `migrations/versions/` and the environment
in `migrations/env.py` (reads `POSTGRES_DSN`, applies the psycopg driver).
`make up` runs `alembic upgrade head` in the `api` service before it starts;
`make migrate` runs it locally against `POSTGRES_DSN` (from the environment or
`.env`). Revisions are tracked in the `alembic_version` table, so each is
applied exactly once. The integration tests run the same revisions via
`alembic.command.upgrade`.

### Config

`Settings` (pydantic-settings) loads from env / `.env`. Key knobs:
`postgres_dsn` (required — no default), `embedding_dim`,
`max_history_pairs`, `embedding_cache_size`, `embedding_batch_size`,
`embedding_cache_ttl_seconds`, `ollama_num_ctx`, `ollama_num_predict`,
`ollama_timeout_seconds`, `db_pool_max_size`, `chunk_tokens`,
`chunk_overlap_ratio`, `log_level`.

### Testing

- **Integration tests** are gated behind `@pytest.mark.integration` and the
  `--integration` flag (see `tests/conftest.py`). They need Docker for PostgreSQL.
- **In-memory fakes** (`tests/in_memory.py`) cover the repositories; model
  provider stubs sit in `tests/use_cases/fakes.py` and in individual tests —
  no Docker needed for unit tests.
- Tests mirror `src/findocbot/`: `infrastructure/chunking.py` →
  `tests/infrastructure/test_chunking.py`, `main.py` → `tests/test_main.py`
  (app wiring smoke). Cross-cutting `tests/test_rag_evaluation.py` sits at the
  root. Test directories are packages, so shared helpers import as
  `tests.factories` (PDF builder), `tests.in_memory` and `tests.use_cases.fakes`.
- Test names follow `test_{what}_{condition}_{expected}`.
- `tests/conftest.py` holds only the `--integration` option and marker. The
  Postgres fixtures (`pg_dsn` via testcontainers, `db_pool`) live in
  `tests/infrastructure/test_postgres_repositories.py`; API tests build an
  `httpx.ASGITransport` around `create_app(container=...)` inline.

Conventions are codified in `.claude/rules/` (see `_LEVELS.md` for rule levels),
vendored from developer-os `rules-library/`; change a module there first, then
copy it here.
Non-obvious technical decisions are logged in `DECISIONS.md`.