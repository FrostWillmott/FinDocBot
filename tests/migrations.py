"""Apply the Alembic migrations to a throwaway test database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"


def _config() -> Config:
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return config


@contextmanager
def _migration_env(dsn: str, embedding_dim: int | None) -> Iterator[None]:
    """Set what Alembic's env.py reads, for the duration of one command.

    A leaked DSN would point later tests at a container that no longer
    exists. ``embedding_dim=None`` leaves EMBEDDING_DIM unset.
    """
    env = {"POSTGRES_DSN": dsn}
    if embedding_dim is not None:
        env["EMBEDDING_DIM"] = str(embedding_dim)
    with mock.patch.dict(os.environ, env):
        if embedding_dim is None:
            os.environ.pop("EMBEDDING_DIM", None)
        yield


def run_migrations(
    dsn: str, embedding_dim: int | None, revision: str = "head"
) -> None:
    """Apply the real migrations up to ``revision`` at ``dsn`` (blocking)."""
    with _migration_env(dsn, embedding_dim):
        command.upgrade(_config(), revision)


def revert_migrations(dsn: str, revision: str) -> None:
    """Roll the real migrations back to ``revision`` at ``dsn`` (blocking)."""
    with _migration_env(dsn, 1024):
        command.downgrade(_config(), revision)
