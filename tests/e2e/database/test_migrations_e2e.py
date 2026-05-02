"""US-011 E2E test for real Alembic migration command flow."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
)

EXPECTED_RUNTIME_TABLES = {
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


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    return subprocess.run(
        ["alembic", *args],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _fetch_public_tables() -> set[str]:
    async def _query() -> set[str]:
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )
            tables = {row[0] for row in result.fetchall()}
        await engine.dispose()
        return tables

    return asyncio.run(_query())


def test_us011_alembic_real_command_flow() -> None:
    """🔁 US-011 E2E: downgrade/upgrade/current/check/downgrade with real Alembic commands."""
    downgrade_initial = _run_alembic("downgrade", "base")
    assert downgrade_initial.returncode == 0, downgrade_initial.stderr

    upgrade = _run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    tables_after_upgrade = _fetch_public_tables()
    assert EXPECTED_RUNTIME_TABLES.issubset(tables_after_upgrade)

    current = _run_alembic("current")
    assert current.returncode == 0, current.stderr
    assert "001_initial_schema" in current.stdout

    check = _run_alembic("check")
    assert check.returncode == 0, check.stderr

    downgrade_final = _run_alembic("downgrade", "base")
    assert downgrade_final.returncode == 0, downgrade_final.stderr

    tables_after_downgrade = _fetch_public_tables()
    assert EXPECTED_RUNTIME_TABLES.isdisjoint(tables_after_downgrade)
