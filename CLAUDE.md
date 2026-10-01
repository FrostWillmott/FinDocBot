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

The CI `test` job runs `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest --cov-fail-under=90`. The `integration` job runs `pytest --integration -m integration` separately.

## Architecture

The project follows **Clean Architecture** with four layers (outer to inner):

```
adapters/api  →  use_cases  →  domain
                      ↓
               infrastructure
```

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

Each has a real implementation in `infrastructure/` and a fake in
`infrastructure/in_memory.py` for tests.

### Caching layer

`CachedEmbeddingGateway` wraps `ModelProviderGateway` with an in-memory TTL cache
(TTLCache from `cachetools`). It only caches `embed_one`/`embed_many`; generation
passes through uncached.

### Key patterns

- **Error mapping**: `adapters/api/routes.py:_map_use_case_errors()` maps domain
  exceptions to HTTP status codes — `ModelProviderError` → 502,
  `InfrastructureError` → 503, `FinDocBotError` → 400.
- **CPU-bound offloading**: PDF parsing and chunking run via `asyncio.to_thread()`
  to avoid blocking the event loop.
- **Embedding dimension**: hardcoded as `VECTOR(768)` in
  `migrations/001_init.sql` to match `nomic-embed-text`; switching the embedding
  model needs a migration.
- **PDF → chunks**: the parser rebuilds paragraph breaks (blank lines) from line
  positions; the chunker treats them as paragraph boundaries and a paragraph
  starting with `Section`/`Chapter` as a section heading that closes the chunk.
- **Document persistence**: the document row is inserted only after embeddings
  succeed; rolled back if chunk insertion fails.

### Config

`Settings` (pydantic-settings) loads from env / `.env`. Key knobs:
`top_k`, `max_history_pairs`, `embedding_cache_size`, `embedding_batch_size`,
`embedding_cache_ttl_seconds`.

### Testing

- **Integration tests** are gated behind `@pytest.mark.integration` and the
  `--integration` flag (see `tests/conftest.py`). They need Docker for PostgreSQL.
- **In-memory fakes** (`infrastructure/in_memory.py`) cover repositories and the
  model provider — no Docker needed for unit tests.
- `tests/conftest.py` holds only the `--integration` option and marker. The
  Postgres fixtures (`pg_dsn` via testcontainers, `db_pool`) live in
  `tests/test_postgres_repositories.py`; API tests build an
  `httpx.ASGITransport` around `create_app(container=...)` inline.
- One flat `tests/test_*.py` file per subsystem.

Conventions are codified in `.claude/rules/` (see `_LEVELS.md` for rule levels).
Non-obvious technical decisions are logged in `DECISIONS.md`.