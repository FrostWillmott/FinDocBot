UV := uv
APP_MODULE := findocbot.main:create_app
APP_FLAGS := --factory

.PHONY: sync dev lint fmt test cover precommit-install up down logs migrate

sync:
	$(UV) sync --all-groups

dev:
	$(UV) run uvicorn $(APP_MODULE) $(APP_FLAGS) --host 0.0.0.0 --port 8000 --reload

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt:
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

test:
	$(UV) run pytest -q

cover:
	$(UV) run pytest -q --cov --cov-report=term-missing

precommit-install:
	$(UV) run pre-commit install

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api db ollama

migrate:
	docker compose exec db psql -U postgres -d findocbot -f /docker-entrypoint-initdb.d/001_init.sql
	docker compose exec db psql -U postgres -d findocbot -f /docker-entrypoint-initdb.d/002_hnsw_index.sql
