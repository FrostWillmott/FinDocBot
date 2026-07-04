"""Application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from findocbot.adapters.api.routes import build_router
from findocbot.config import load_settings
from findocbot.infrastructure.container import AppContainer, create_container


def create_app(
    container: AppContainer | None = None,
) -> FastAPI:
    """Create configured FastAPI app.

    Args:
        container: Optional pre-built container for testing. When ``None``,
            a production container is created from settings.
    """
    if container is None:
        settings = load_settings()
        container = create_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        await container.startup()
        yield
        await container.shutdown()

    app = FastAPI(title="FinDocBot API", version="0.1.0", lifespan=lifespan)
    app.include_router(build_router(container))

    return app


def run() -> None:
    """Run the application with the default host and port."""
    uvicorn.run(
        "findocbot.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
