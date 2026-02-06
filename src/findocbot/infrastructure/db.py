"""PostgreSQL connection management."""

import asyncpg


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
