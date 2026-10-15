"""E2E fixtures: real Postgres and a real Ollama, plus a wired app client."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import asyncpg
import httpx
import pytest
from testcontainers.ollama import OllamaContainer
from testcontainers.postgres import PostgresContainer

from findocbot.config import Settings
from findocbot.infrastructure.container import create_container
from findocbot.main import create_app
from tests.migrations import run_migrations

# docker-compose.yml leads for both image tags; bump them there first.
_POSTGRES_IMAGE = "pgvector/pgvector:pg16"
_OLLAMA_IMAGE = "ollama/ollama:0.35.1"
# Pinned to a tag (Settings defaults to ":latest") so a re-pushed model
# cannot shift retrieval underneath the figure the search test looks for.
_EMBED_MODEL = "nomic-embed-text:v1.5"
# A real-but-tiny chat model: small enough to pull in CI, and Ollama's
# ``format`` schema still constrains it to valid JSON.
_CHAT_MODEL = "qwen2.5:0.5b"


@pytest.fixture(scope="session")
def e2e_settings() -> Iterator[Settings]:
    """Spin up Postgres and Ollama once for the whole e2e session."""
    # ``with`` stops both containers even when a pull or migration fails
    # before the yield; Ryuk alone cannot be relied on (it is often disabled
    # under podman and rootless Docker).
    with (
        PostgresContainer(_POSTGRES_IMAGE, dbname="findocbot") as postgres,
        OllamaContainer(image=_OLLAMA_IMAGE) as ollama,
    ):
        for model in (_EMBED_MODEL, _CHAT_MODEL):
            # Not ``pull_model``: it discards the exit code, so a failed
            # pull would surface later as an unrelated embed error.
            result = ollama.exec(["ollama", "pull", model])
            if result.exit_code != 0:
                raise RuntimeError(f"ollama pull {model}: {result.output!r}")

        # _env_file=None: a developer's .env must not change what CI runs.
        settings = Settings(
            _env_file=None,
            postgres_dsn=postgres.get_connection_url(driver=None),
            ollama_base_url=ollama.get_endpoint(),
            ollama_embed_model=_EMBED_MODEL,
            ollama_chat_model=_CHAT_MODEL,
        )
        run_migrations(str(settings.postgres_dsn), settings.embedding_dim)
        yield settings


@pytest.fixture
async def client(
    e2e_settings: Settings,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """A real container behind an HTTP client; the lifespan runs the worker."""
    # The database lives for the whole session; wipe it so every test starts
    # without documents (a re-upload of the same PDF would otherwise be
    # deduplicated to the earlier test's row).
    connection = await asyncpg.connect(str(e2e_settings.postgres_dsn))
    try:
        await connection.execute(
            "TRUNCATE chunks, documents, chat_turns, sessions"
        )
    finally:
        await connection.close()

    app = create_app(container=create_container(e2e_settings))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
