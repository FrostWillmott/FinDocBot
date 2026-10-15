# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run through `make` — the Makefile is the source of truth for
targets (`sync`, `dev`, `lint`, `fmt`, `test`, `cover`, `up`, `down`, `logs`,
`migrate`, `precommit-install`). Two checks have no make target:

- Integration tests (Docker): `uv run pytest -q --integration -m integration`
- Type check: `uv run mypy src/findocbot`

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

Each has a real implementation in `infrastructure/`. Repository fakes live in
`tests/in_memory.py`, provider stubs in the tests that use them; neither ships
in the package. `adapters/api/routes.py` depends on the `ApiServices` Protocol,
not on `AppContainer`, so the API layer never imports `infrastructure`.

### Caching layer

`CachedEmbeddingGateway` wraps `ModelProviderGateway` with a hand-rolled LRU
cache with TTL (an `OrderedDict`, no third-party cache library). It caches only
`embed_one` (query embeddings); `embed_many` and generation pass through uncached.

### Key patterns

Current-state index — `DECISIONS.md` is the append-only *why* log; when a
decision there is superseded, refresh the corresponding line here.

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
- **Background ingestion**: `IngestionUseCase` owns the whole lifecycle, with
  no port for its queue. `POST /documents/upload` calls `submit`, which stores a
  `pending` document and enqueues the bytes on a private in-process asyncio
  queue; the container starts the worker via `start()`/`stop()`. The worker
  parses, chunks, embeds and persists them, then flips the status to `ready`
  or `failed` (with a client-safe `error`); an error nobody anticipated
  also ends as `failed`, with a fixed message and its traceback in the log.
  Tests run queued work with `drain()`. Terms are in `CONTEXT.md`. A SHA-256 of the uploaded bytes
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

`Settings` (pydantic-settings, `src/findocbot/config.py`) loads from env /
`.env`; the class is the source of truth for field names and defaults.
`postgres_dsn` is required (no default). `CHUNK_TOKENS` is coupled to
`OLLAMA_NUM_CTX` and the per-source prompt cap (`_MAX_SOURCE_CHARS`), so raise
them together — `.env.example` says so next to the setting.

### Testing

- Tests use a three-layer layout — `tests/unit/` (no I/O), `tests/integration/`
  (real DB), `tests/e2e/` (HTTP surface) — mirroring `src/findocbot/` within
  each layer.
- **Integration tests** (`@pytest.mark.integration`, `--integration`) need Docker
  for PostgreSQL; **e2e tests** (`@pytest.mark.e2e`, `--e2e`) need Docker plus a
  real Ollama. Each is skipped unless its flag is passed (see `tests/conftest.py`);
  CI runs them in separate jobs.
- **In-memory fakes** (`tests/in_memory.py`) cover the repositories; model
  provider stubs sit in `tests/fakes.py` and in individual tests — no Docker
  needed for unit tests.
- Shared helpers live at the `tests/` root: `tests.factories` (PDF builder),
  `tests.in_memory`, `tests.fakes` and `tests.migrations` (Alembic helper).
- Test names follow `test_{what}_{condition}_{expected}`.
- `tests/conftest.py` holds only the `--integration`/`--e2e` options and markers.
  The Postgres fixtures live in `tests/integration/test_postgres_repositories.py`;
  the e2e infra (real Postgres + Ollama) is in `tests/e2e/conftest.py`; API
  adapter tests build an `httpx.ASGITransport` around `create_app(container=...)`.

Conventions are codified in `.claude/rules/` (see `_LEVELS.md` for rule levels),
vendored from developer-os `rules-library/`; change a module there first, then
copy it here.
Non-obvious technical decisions are logged in `DECISIONS.md`.

## Agent skills

Skills ship via the `mattpocock-skills` Claude Code plugin (project scope), not files in this repo.

### Issue tracker

Issues live in GitHub Issues for `FrostWillmott/FinDocBot`; skills read and write them via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

`CONTEXT.md` (glossary) and `docs/adr/` don't exist until `/domain-modeling`
creates them lazily. See `docs/agents/domain.md`.