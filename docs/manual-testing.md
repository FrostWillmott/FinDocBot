# FinDocBot — Manual Testing Checklist

A step-by-step manual verification of the system, from static checks to the
full end-to-end RAG scenario (upload → search → ask), including failure
scenarios.

All commands are run from the repository root.

---

## 0. Prerequisites

- Python 3.12+, `uv`, Docker + Docker Compose.
- Free ports: `8000` (API), `5432` (Postgres), `11434` (Ollama).
- ~5–6 GB of disk space for Ollama models (`qwen2.5:7b`, `nomic-embed-text`).

Environment check:

```bash
uv --version
docker --version
docker compose version
```

---

## 1. Static checks (no external services)

The quickest way to confirm the code builds and types/style are in order.

```bash
uv sync --all-groups          # install dependencies
uv run ruff check .           # linter  -> All checks passed!
uv run ruff format --check .  # format  -> N files already formatted
uv run mypy src/findocbot     # types   -> Success: no issues found
uv run pytest -q              # tests   -> 51 passed, 4 skipped
```

Expected: `4 skipped` — these are the PostgreSQL integration tests, which
require Docker.

To run them too (spins up a temporary Postgres via testcontainers):

```bash
uv run pytest --integration -q
```

Coverage report (CI enforces ≥90%):

```bash
make cover
```

Verify the application imports and routes are registered:

```bash
uv run python -c "
from findocbot.main import create_app
from findocbot.config import load_settings
from findocbot.infrastructure.container import create_container
app = create_app(create_container(load_settings()))
print(sorted(r.path for r in app.routes if hasattr(r, 'path')))
"
# -> [..., '/ask', '/documents/upload', '/health', '/search', ...]
```

---

## 2. Bring up infrastructure (Postgres + Ollama)

First create `.env` — the `api` service in compose requires `env_file`:

```bash
cp .env.example .env
```

```bash
make up          # starts db, ollama, api (builds the image)
docker compose ps
```

Wait until `findocbot-db` and `findocbot-ollama` report `healthy`.
On first start Ollama **downloads the models** — this takes a while
(several minutes). To watch progress:

```bash
make logs        # Ctrl+C to exit the logs (services keep running)
```

Confirm the models were pulled:

```bash
curl -s http://localhost:11434/api/tags | python3 -m json.tool
# the list should include qwen2.5:7b and nomic-embed-text
```

---

## 3. Run the API

There are two options — pick one.

### Option A. API inside Docker (simplest)

`make up` already started the `api` service. Check:

```bash
curl -s http://localhost:8000/health
# -> {"status":"ok"}
```

### Option B. API locally (`make dev`)

> ℹ️ `.env.example` points at `localhost`, so for a local run you can safely
> `cp .env.example .env`. The Docker setup is unaffected: the `api` service in
> `docker-compose.yml` overrides `OLLAMA_BASE_URL` and `POSTGRES_DSN` with
> docker-network hosts (`ollama`/`db`) via `environment:`.

Run:

```bash
make dev
curl -s http://localhost:8000/health   # in another terminal -> {"status":"ok"}
```

Swagger UI for manual requests: http://localhost:8000/docs

---

## 4. End-to-end RAG scenario

### 4.1 Prepare a test PDF

If you don't have a financial PDF at hand, generate a simple one
(fpdf2 is already in the dev dependencies):

```bash
uv run python -c "
from fpdf import FPDF
pdf = FPDF()
pdf.add_page()
pdf.set_font('Helvetica', size=12)
text = '''Section 1. Financial Results.

The company revenue in Q2 2023 was 120 million dollars.
Net profit for 2023 reached 25 million dollars, up 20 percent year over year.

Section 2. Outlook.

Management expects revenue growth to continue into 2024.'''
for line in text.split(chr(10)):
    pdf.multi_cell(0, 8, line)
pdf.output('sample.pdf')
print('written sample.pdf')
"
```

### 4.2 Upload the document

```bash
curl -s -X POST "http://localhost:8000/documents/upload" \
     -F "file=@sample.pdf" | python3 -m json.tool
# -> {"document_id": "<uuid>", "filename": "sample.pdf"}
```

Negative scenario:

```bash
# non-PDF -> 400
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
     "http://localhost:8000/documents/upload" -F "file=@README.md"   # -> 400
```

### 4.3 Semantic search

```bash
curl -s -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "net profit for 2023", "top_k": 3}' | python3 -m json.tool
# -> a list of chunks with text/score/section fields, score descending
```

### 4.4 Question answering (RAG + structured output)

```bash
curl -s -X POST "http://localhost:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "What was the company revenue in Q2?",
          "session_id": "demo-1", "top_k": 3}' | python3 -m json.tool
# -> {"answer": "...120 million...", "confidence": "high|medium|low", "sources": [...]}
```

Check that `confidence` is one of {high, medium, low} and `sources` is
non-empty.

### 4.5 Dialogue memory (session history)

Ask a follow-up question in the same session — the answer should take the
context into account:

```bash
curl -s -X POST "http://localhost:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "And what about net profit?",
          "session_id": "demo-1", "top_k": 3}' | python3 -m json.tool
```

Verify the history is written to the database:

```bash
docker compose exec db psql -U postgres -d findocbot \
  -c "SELECT session_id, question FROM chat_turns ORDER BY created_at;"
```

---

## 5. Inspect data in the database (optional)

```bash
docker compose exec db psql -U postgres -d findocbot -c "\dt"
docker compose exec db psql -U postgres -d findocbot \
  -c "SELECT count(*) FROM documents;"
docker compose exec db psql -U postgres -d findocbot \
  -c "SELECT count(*) FROM chunks;"
# Confirm the HNSW index exists:
docker compose exec db psql -U postgres -d findocbot \
  -c "\di idx_chunks_embedding_hnsw"
```

---

## 6. Failure-mode checks

- **Ollama down** → `docker compose stop ollama`, then repeat `/ask` or
  `/search`. Expected: HTTP `502` (`ModelProviderError`), not `500`.
- **Postgres down** → `docker compose stop db`, then repeat `/search`.
  Expected: HTTP `503` (`StorageError`).
- **Empty query** → `{"query": "", "top_k": 3}` to `/search`.
  Expected: `422` (Pydantic validation, `min_length=1`).

Don't forget to bring the services back: `docker compose start ollama db`.

---

## 7. Teardown

```bash
make down          # stop and remove containers
# docker compose down -v   # + remove volumes (full wipe of DB and models)
rm -f sample.pdf
```

---

## "It works" checklist

- [ ] `ruff`, `mypy`, `pytest` are green
- [ ] `/health` returns `{"status":"ok"}`
- [ ] PDF upload returns a `document_id`
- [ ] `/search` returns relevant chunks with descending score
- [ ] `/ask` returns `answer` + valid `confidence` + `sources`
- [ ] Dialogue history is persisted in `chat_turns`
- [ ] Ollama/Postgres outages yield 502/503, not 500