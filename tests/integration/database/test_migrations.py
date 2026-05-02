"""Integration tests for Alembic migrations (US-011)."""

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

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
)

EXPECTED_TABLES = {
    "flows",
    "tasks",
    "subtasks",
    "containers",
    "toolcalls",
    "msgchains",
    "termlogs",
    "msglogs",
    "vector_store",
}

EXPECTED_ENUMS = {
    "flow_status",
    "task_status",
    "subtask_status",
    "container_type",
    "container_status",
    "toolcall_status",
    "msgchain_type",
    "termlog_type",
    "msglog_type",
    "msglog_result_format",
}

EXPECTED_TRIGGER_TABLES = {
    "flows",
    "tasks",
    "subtasks",
    "containers",
    "toolcalls",
    "msgchains",
}


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def _run_alembic_upgrade_head() -> None:
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url


def _run_alembic_downgrade_base() -> None:
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.downgrade(_alembic_config(), "base")
    finally:
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url


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


def _downgrade_base_if_present() -> None:
    if not _has_alembic_version_row():
        return

    # A partially reset local DB can leave revision metadata inconsistent.
    # In that case we rely on force reset before the next upgrade.
    with suppress(CommandError):
        _run_alembic_downgrade_base()


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


def _run_alembic_check() -> None:
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.check(_alembic_config())
    finally:
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url


@pytest.fixture()
def migrated_schema():
    _downgrade_base_if_present()
    _force_reset_runtime_schema()
    _run_alembic_upgrade_head()
    yield
    _downgrade_base_if_present()
    _force_reset_runtime_schema()


@pytest.fixture()
async def migrated_db(migrated_schema):
    await init_db(TEST_DATABASE_URL, echo=False)
    yield
    await close_db()


async def test_alembic_upgrade_head_creates_runtime_tables(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
        )
        existing_tables = {row[0] for row in result.fetchall()}

    assert EXPECTED_TABLES.issubset(existing_tables)


def test_alembic_downgrade_base_drops_runtime_tables(migrated_schema) -> None:
    _run_alembic_downgrade_base()

    async def _assert_tables_dropped() -> None:
        await init_db(TEST_DATABASE_URL, echo=False)
        async with get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )
            existing_tables = {row[0] for row in result.fetchall()}
        await close_db()
        assert EXPECTED_TABLES.isdisjoint(existing_tables)

    asyncio.run(_assert_tables_dropped())


def test_alembic_upgrade_head_is_idempotent() -> None:
    _downgrade_base_if_present()
    _force_reset_runtime_schema()

    _run_alembic_upgrade_head()
    _run_alembic_upgrade_head()
    _downgrade_base_if_present()
    _force_reset_runtime_schema()


async def test_required_enum_types_exist_after_migration(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT typname
                FROM pg_type
                WHERE typname = ANY(:types)
                """
            ),
            {"types": list(EXPECTED_ENUMS)},
        )
        existing_types = {row[0] for row in result.fetchall()}

    assert existing_types == EXPECTED_ENUMS


async def test_update_modified_column_function_exists(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT proname
                FROM pg_proc
                WHERE proname = 'update_modified_column'
                """
            )
        )

    assert result.fetchone() is not None


async def test_update_triggers_attached_to_runtime_tables(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT DISTINCT event_object_table
                FROM information_schema.triggers
                WHERE trigger_name LIKE 'tr_%_updated_at'
                """
            )
        )
        trigger_tables = {row[0] for row in result.fetchall()}

    assert trigger_tables == EXPECTED_TRIGGER_TABLES


async def test_pgvector_extension_installed_after_migration(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )

    assert result.fetchone() is not None


def test_alembic_check_reports_no_pending_migrations() -> None:
    _downgrade_base_if_present()
    _force_reset_runtime_schema()

    _run_alembic_upgrade_head()
    _run_alembic_check()
    _downgrade_base_if_present()
    _force_reset_runtime_schema()
