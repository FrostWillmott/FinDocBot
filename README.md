# 🤖 FinDocBot

[![CI](https://github.com/FrostWillmott/FinDocBot/actions/workflows/ci.yml/badge.svg)](https://github.com/FrostWillmott/FinDocBot/actions)
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
- ⚡ **High Performance**: Embedding caching and efficient PDF processing.

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
   cd findocbot
   ```

2. **Configure environment**:
   Install dependencies and prepare the virtual environment:
   ```bash
   make sync
   ```

3. **Start infrastructure**:
   Spin up PostgreSQL and Ollama via Docker Compose:
   ```bash
   make up
   ```

4. **Pull models in Ollama**:
   If you are using Ollama in Docker or locally, ensure the models are downloaded:
   ```bash
   docker exec -it findocbot-ollama ollama pull qwen2.5:7b
   docker exec -it findocbot-ollama ollama pull nomic-embed-text
   ```

5. **Run the API**:
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

## 🧪 Testing & Code Quality

- **Run tests**: `make test`
- **Linting & Formatting**: `make lint` / `make fmt`

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🇷🇺 Russian Version / Русская версия

<details>
<summary>Посмотреть README на русском языке</summary>

# 🤖 FinDocBot

**FinDocBot** — это современная RAG-система (Retrieval-Augmented Generation) на базе чистой архитектуры, предназначенная для семантического поиска и ответов на вопросы по финансовым PDF-документам.

Проект использует локальные LLM через **Ollama** и векторное хранилище **PostgreSQL (pgvector)** для обеспечения конфиденциальности данных и высокой производительности.

## 🚀 Основные возможности

- 📁 **Загрузка PDF**: автоматический парсинг и индексация финансовых отчетов.
- 🔍 **Семантический поиск**: поиск релевантных фрагментов текста по смыслу, а не только по ключевым словам.
- 💬 **Контекстный чат**: генерация ответов на вопросы с учетом истории диалога и найденных источников.
- 🏗️ **Clean Architecture**: четкое разделение бизнес-логики, домена и инфраструктуры.
- ⚡ **High Performance**: эмбеддинги кешируются, а PDF обрабатываются максимально эффективно.

## 🛠 Технологический стек

- **Язык**: Python 3.12+
- **API Framework**: FastAPI
- **LLM/Embeddings**: Ollama (модели `qwen2.5:7b` и `nomic-embed-text`)
- **База данных**: PostgreSQL + pgvector
- **Парсинг PDF**: PyPDF
- **Управление зависимостями**: [uv](https://github.com/astral-sh/uv)
- **Контейнеризация**: Docker & Docker Compose

## 🏗 Архитектура

Проект построен по принципам **Clean Architecture**:

- `src/findocbot/domain`: Доменные модели и сущности.
- `src/findocbot/use_cases`: Бизнес-логика приложения (интерфейсы и реализация сценариев).
- `src/findocbot/infrastructure`: Внешние реализации (БД, Ollama, парсеры).
- `src/findocbot/adapters`: Внешние интерфейсы (REST API).

</details>
