"""PostgreSQL connection management."""

from __future__ import annotations

import asyncpg

from findocbot.domain.exceptions import StorageError


class PostgresPool:
    """Thin wrapper around asyncpg pool lifecycle."""

    def __init__(self, dsn: str) -> None:
        """Create pool wrapper with connection string."""
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        """Create asyncpg pool if missing."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn, min_size=1, max_size=5
            )

    async def stop(self) -> None:
        """Close asyncpg pool if created."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Expose initialized pool."""
        if self._pool is None:
            raise RuntimeError("Postgres pool is not initialized.")
        return self._pool

    async def ping(self, timeout_seconds: float = 2.0) -> None:
        """Run a trivial query; raise StorageError if the DB is down."""
        try:
            # Timeout on acquire: a saturated pool must not hang the probe.
            async with self.pool.acquire(timeout=timeout_seconds) as conn:
                await conn.fetchval("SELECT 1", timeout=timeout_seconds)
        except (
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            OSError,
            TimeoutError,
        ) as exc:
            raise StorageError("Database is unavailable") from exc
