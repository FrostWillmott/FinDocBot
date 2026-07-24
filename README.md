# 🤖 FinDocBot

[![CI](https://github.com/FrostWillmott/FinDocBot/actions/workflows/ci.yml/badge.svg)](https://github.com/FrostWillmott/FinDocBot/actions)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/FrostWillmott/FinDocBot/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FinDocBot** is a modern RAG (Retrieval-Augmented Generation) system built with Clean Architecture, designed for semantic search and question-answering over financial PDF documents.

The project leverages local LLMs via **Ollama** and **PostgreSQL (pgvector)** for vector storage, ensuring data privacy and high performance.

---

## 🚀 Key Features

- 📁 **PDF Upload**: Automatic parsing and indexing of financial reports.
- 🔍 **Semantic Search**: Find relevant text fragments based on meaning, not just keywords.
- 💬 **Contextual Chat**: Generate answers to questions considering dialogue history and retrieved sources.
- 🏗️ **Clean Architecture**: Strict separation of business logic, domain, and infrastructure for maintainability and testability.
- ⚡ **High Performance**: Embedding caching, HNSW vector index, and efficient PDF processing.
- 🧪 **RAG Evaluation**: Built-in faithfulness and retrieval precision metrics over a golden Q&A dataset.
- 🗂️ **Structured Output**: LLM responses are constrained to a JSON Schema (answer + confidence level) via Ollama's `format` field.

---

## 🛠 Tech Stack

- **Language**: Python 3.12+
- **API Framework**: FastAPI
- **LLM/Embeddings**: Ollama (models `qwen2.5:7b` and `nomic-embed-text`)
- **Database**: PostgreSQL + pgvector
- **PDF Parsing**: PyPDF
- **Dependency Management**: [uv](https://github.com/astral-sh/uv)
- **Containerization**: Docker & Docker Compose

---

## 🏁 Quick Start

### Prerequisites
1. [Docker](https://www.docker.com/) and Docker Compose installed.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) installed.
3. [Ollama](https://ollama.com/) installed (if running Ollama locally instead of in Docker).

### Setup Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/FrostWillmott/FinDocBot.git
   cd FinDocBot
   ```

2. **Configure environment**:
   Install dependencies and prepare the virtual environment:
   ```bash
   make sync
   ```

3. **Start infrastructure**:
   Spin up PostgreSQL and Ollama via Docker Compose (models are pulled automatically):
   ```bash
   make up
   ```

4. **Run the API**:
   ```bash
   make dev
   ```
   The API will be available at: `http://localhost:8000`. Swagger documentation: `http://localhost:8000/docs`.

---

## 📖 API Documentation

### Upload Document
`POST /documents/upload` — Uploads a PDF file for indexing.

```bash
curl -X POST "http://localhost:8000/documents/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@/path/to/report.pdf"
```

### Search Document
`POST /search` — Search for relevant text fragments.

```bash
curl -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "Net profit for 2023", "top_k": 3}'
```

### Ask Question
`POST /ask` — Generate an answer based on document context.

```bash
curl -X POST "http://localhost:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "What was the company revenue in Q2?",
       "session_id": "user-session-123"
     }'
```

---

## 🏗 Architecture

The project strictly follows **Clean Architecture** principles, ensuring the core business logic remains independent of external frameworks, databases, and UI:

- **Domain Layer (`src/findocbot/domain`)**: Contains enterprise-wide business rules, entities, and custom exceptions. This layer has zero dependencies on other layers.
- **Use Cases Layer (`src/findocbot/use_cases`)**: Implements application-specific business logic (e.g., uploading a PDF, searching chunks). Defines **Ports** (interfaces) for infrastructure.
- **Infrastructure Layer (`src/findocbot/infrastructure`)**: Concrete implementations of ports. Handles database persistence (PostgreSQL), external API calls (Ollama), and file parsing.
- **Adapters Layer (`src/findocbot/adapters`)**: Translates data between the use cases and external delivery mechanisms (REST API via FastAPI).

This decoupling allows for easy testing (e.g., swapping PostgreSQL for an in-memory DB) and long-term maintainability.

---

## ⚡ Vector Index

PostgreSQL uses an **HNSW** index (`m=16, ef_construction=64`) over the
`chunks.embedding` column for fast approximate nearest-neighbour search.
The migration is applied automatically by `docker compose up` and
`make migrate`.

---

## 🗂️ Structured Output

`POST /ask` returns a `confidence` field (`high` / `medium` / `low`) alongside the answer.
The LLM is constrained via Ollama's `format` parameter to emit a JSON object matching the
schema, and the response is validated with Pydantic before reaching the client:

```json
{
  "answer": "Revenue grew by 20 percent.",
  "confidence": "high"
}
```

---

## 🧪 RAG Evaluation

`tests/test_rag_evaluation.py` demonstrates a methodology for measuring retrieval
precision and faithfulness over a golden Q&A dataset. It runs against the
in-memory stack (no external services) using deterministic fake embeddings and
answers.

| Metric | Definition | Threshold |
|--------|-----------|-----------|
| **Retrieval Precision** | Fraction of retrieved chunks containing a keyword relevant to the question | ≥ 0.50 |
| **Faithfulness** | Fraction of answer keywords that appear in the retrieved context | ≥ 0.50 |

> The evaluation uses keyword-based fake providers to illustrate metric
> computation. For production use, replace them with real Ollama embeddings
> and answers, and define a proper golden dataset.

Run the evaluation:
```bash
make test
```

---

## 🧪 Testing & Code Quality

- **Run tests**: `make test` (add `--integration` for PostgreSQL tests via Docker; CI runs them in a separate job)
- **Coverage report**: `make cover` (pytest-cov, terminal report with missing lines; CI enforces ≥80%)
- **Linting & Formatting**: `make lint` / `make fmt`
- **Static type checking**: `uv run mypy src/findocbot` (strict mode, enforced in CI)

---

## 📚 Documentation

- [Runbook](docs/runbook.md) — bring-up/teardown, quality checks, migrations.
- [Manual testing checklist](docs/manual-testing.md) — full E2E pass, including failure modes (Ollama down → 502, Postgres down → 503).
- [Optimizations](docs/optimizations.md) — embedding and vector-search performance notes.
- [DECISIONS.md](DECISIONS.md) — append-only log of non-obvious technical decisions.

Coding conventions (typing, error handling, testing, pgvector and LLM-integration rules) are codified in [`.claude/rules/`](.claude/rules/) as small binding modules with explicit rule levels (see `_LEVELS.md`); they serve both human contributors and AI-assisted tooling.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

