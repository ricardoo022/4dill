"""Alembic async migration environment for SQLAlchemy models."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from pentest.database.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure_database_url() -> None:
    """Resolve DATABASE_URL and inject it into Alembic config."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for Alembic")

    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    _configure_database_url()
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with an established SQLAlchemy connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""

    _configure_database_url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online_entrypoint() -> None:
    """Run online migrations across Alembic/runtime compatibility modes."""

    run_async = getattr(context, "run_async", None)
    if callable(run_async):
        run_async(run_migrations_online)
        return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_migrations_online())
        return

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(run_migrations_online()))
        future.result()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online_entrypoint()
