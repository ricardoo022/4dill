"""US-011 unit tests for Alembic configuration scaffolding."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_alembic_ini_uses_database_url_placeholder() -> None:
    """US-011: alembic.ini resolves sqlalchemy.url from DATABASE_URL placeholder."""
    alembic_ini = ROOT / "alembic.ini"
    content = alembic_ini.read_text(encoding="utf-8")

    assert "sqlalchemy.url = %(DATABASE_URL)s" in content


def test_alembic_scaffold_exists_for_runtime_migrations() -> None:
    """US-011: project contains Alembic root, env.py, and versions directory."""
    assert (ROOT / "alembic").is_dir()
    assert (ROOT / "alembic" / "env.py").is_file()
    assert (ROOT / "alembic" / "versions").is_dir()
