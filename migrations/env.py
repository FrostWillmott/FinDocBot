"""Alembic migration environment.

The database URL is read from ``POSTGRES_DSN`` (the same variable the app
uses). A bare ``postgresql://`` DSN is rewritten to ``postgresql+psycopg``
because the migrations run over the psycopg driver, while asyncpg (which
uses the same DSN scheme) is reserved for the runtime pool.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

config = context.config

dsn = os.environ.get("POSTGRES_DSN")
if not dsn:
    raise RuntimeError("POSTGRES_DSN must be set to run migrations.")
url = make_url(dsn)
if url.drivername == "postgresql":
    url = url.set(drivername="postgresql+psycopg")

# Migrations are written as raw SQL (op.execute), so no metadata is needed.
target_metadata = None


def run_migrations_offline() -> None:
    """Emit the SQL without connecting (``alembic upgrade --sql``)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply pending revisions."""
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
