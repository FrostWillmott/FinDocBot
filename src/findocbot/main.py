"""Application entrypoint."""

import uvicorn
from fastapi import FastAPI

from findocbot.adapters.api.routes import build_router
from findocbot.config import load_settings
from findocbot.infrastructure.container import create_container


def create_app() -> FastAPI:
    """Create configured FastAPI app."""
    settings = load_settings()
    container = create_container(settings)
    app = FastAPI(title="FinDocBot API", version="0.1.0")
    app.state.container = container
    app.include_router(build_router(container))

    @app.on_event("startup")
    async def startup_event() -> None:
        await container.startup()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await container.shutdown()

    return app


app = create_app()


def run() -> None:
    """Run application with default host and port."""
    uvicorn.run("findocbot.main:app", host="0.0.0.0", port=8000, reload=False)
