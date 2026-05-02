"""Shared fixtures for integration database tests."""

import asyncio
import os
from contextlib import suppress
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pentest.database.connection import close_db, get_session, init_db

# Test database URL - uses DATABASE_URL from CI, or defaults for local development
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
)

ROOT = Path(__file__).resolve().parents[3]


def _get_alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def _force_reset_runtime_schema() -> None:
    async def _reset() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS vector_store CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS termlogs CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS msglogs CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS msgchains CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS toolcalls CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS containers CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS subtasks CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS tasks CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS flows CASCADE"))
            await conn.execute(text("DROP FUNCTION IF EXISTS update_modified_column()"))
            await conn.execute(text("DROP TYPE IF EXISTS msglog_result_format CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS msglog_type CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS termlog_type CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS msgchain_type CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS toolcall_status CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS container_status CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS container_type CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS subtask_status CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS task_status CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS flow_status CASCADE"))
        await engine.dispose()

    asyncio.run(_reset())


def _has_alembic_version_row() -> bool:
    async def _check() -> bool:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'alembic_version'
                        """
                    )
                )
                table_exists = result.scalar() is not None
                if not table_exists:
                    return False

                version_row = await conn.execute(text("SELECT version_num FROM alembic_version"))
                return version_row.first() is not None
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def _downgrade_base_if_present(alembic_cfg: Config) -> None:
    if not _has_alembic_version_row():
        return

    # Local dirty state can desync revision metadata from real schema.
    # Force reset handles this before next upgrade.
    with suppress(CommandError):
        command.downgrade(alembic_cfg, "base")


@pytest.fixture(scope="module")
def db_schema():
    """Create database schema from Alembic migrations for this module."""
    alembic_cfg = _get_alembic_config()
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    _downgrade_base_if_present(alembic_cfg)
    _force_reset_runtime_schema()

    command.upgrade(alembic_cfg, "head")
    yield

    _downgrade_base_if_present(alembic_cfg)
    _force_reset_runtime_schema()
    if old_database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = old_database_url


@pytest.fixture()
async def db_session(db_schema):
    """Provide a fresh database session for each test."""
    await init_db(TEST_DATABASE_URL, echo=False)

    # Yield to the test
    yield

    # Clean up after test: Delete all data
    async with get_session() as session:
        # Delete all rows from all tables (order matters due to FK constraints)
        await session.execute(text("DELETE FROM vector_store"))
        await session.execute(text("DELETE FROM termlogs"))
        await session.execute(text("DELETE FROM msglogs"))
        await session.execute(text("DELETE FROM msgchains"))
        await session.execute(text("DELETE FROM toolcalls"))
        await session.execute(text("DELETE FROM containers"))
        await session.execute(text("DELETE FROM subtasks"))
        await session.execute(text("DELETE FROM tasks"))
        await session.execute(text("DELETE FROM flows"))
        await session.commit()

    await close_db()
