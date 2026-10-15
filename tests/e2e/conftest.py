"""E2E fixtures: real Postgres and a real Ollama, plus a wired app client."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer

from findocbot.config import Settings
from findocbot.infrastructure.container import create_container
from findocbot.main import create_app
from tests.migrations import run_migrations

EMBEDDING_DIM = 768
_EMBED_MODEL = "nomic-embed-text"
# A real-but-tiny chat model: small enough to pull in CI, and Ollama's
# ``format`` schema still constrains it to valid JSON.
_CHAT_MODEL = "qwen2.5:0.5b"


def _wait_for_ollama(base_url: str) -> None:
    """Poll until the Ollama daemon answers; pulling needs a live server."""
    for _ in range(60):
        try:
            if (
                httpx.get(f"{base_url}/api/version", timeout=2).status_code
                == 200
            ):
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Ollama server did not become ready")


@pytest.fixture(scope="session")
def e2e_settings() -> Iterator[Settings]:
    """Spin up Postgres and Ollama once for the whole e2e session."""
    postgres = PostgresContainer("pgvector/pgvector:pg16", dbname="findocbot")
    postgres.start()
    dsn = postgres.get_connection_url(driver=None)
    run_migrations(dsn, EMBEDDING_DIM)

    ollama = DockerContainer("ollama/ollama:0.35.1")
    ollama.with_exposed_ports(11434)
    ollama.start()
    base_url = f"http://localhost:{ollama.get_exposed_port(11434)}"
    _wait_for_ollama(base_url)
    for model in (_EMBED_MODEL, _CHAT_MODEL):
        result = ollama.exec(["ollama", "pull", model])
        if result.exit_code != 0:
            raise RuntimeError(f"ollama pull {model}: {result.output!r}")

    yield Settings(
        postgres_dsn=dsn,
        ollama_base_url=base_url,
        ollama_embed_model=_EMBED_MODEL,
        ollama_chat_model=_CHAT_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )

    ollama.stop()
    postgres.stop()


@pytest.fixture
async def client(
    e2e_settings: Settings,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """A real container behind an HTTP client; the lifespan runs the worker."""
    app = create_app(container=create_container(e2e_settings))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
