"""Apply the Alembic migrations to a throwaway test database."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"


def run_migrations(dsn: str, embedding_dim: int) -> None:
    """Apply the real migrations to the database at ``dsn`` (blocking).

    Alembic's env.py reads POSTGRES_DSN and EMBEDDING_DIM from the
    environment, so both are set for the duration of ``upgrade head`` only:
    a leaked DSN would point later tests at a container that no longer exists.
    """
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    with mock.patch.dict(
        os.environ,
        {"POSTGRES_DSN": dsn, "EMBEDDING_DIM": str(embedding_dim)},
    ):
        command.upgrade(config, "head")
