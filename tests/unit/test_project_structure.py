"""US-005: Project Skeleton and Package Structure tests.

Validates pyproject.toml configuration, module imports, docstrings,
and directory structure.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# --- pyproject.toml ---


def _load_pyproject() -> dict:
    """Load and parse pyproject.toml."""
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_pyproject_toml_exists():
    """pyproject.toml exists at project root and is valid TOML."""
    data = _load_pyproject()
    assert "project" in data
    assert "build-system" in data


def test_pyproject_metadata():
    """Project metadata: name, version, python_requires are correct."""
    project = _load_pyproject()["project"]
    assert project["name"] == "securedev-pentest"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.12"


REQUIRED_RUNTIME_DEPS = [
    "sqlalchemy",
    "asyncpg",
    "pgvector",
    "docker",
    "langchain",
    "pydantic",
    "jinja2",
    "alembic",
    "structlog",
]


def test_pyproject_has_runtime_dependencies():
    """All core runtime dependencies are listed in [project.dependencies]."""
    deps = _load_pyproject()["project"]["dependencies"]
    deps_lower = [d.lower() for d in deps]
    for pkg in REQUIRED_RUNTIME_DEPS:
        assert any(pkg in d for d in deps_lower), f"Missing runtime dependency: {pkg}"


REQUIRED_DEV_DEPS = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy",
    "testcontainers",
]


def test_pyproject_has_dev_dependencies():
    """Dev extras include all required test and lint tools."""
    dev_deps = _load_pyproject()["project"]["optional-dependencies"]["dev"]
    dev_lower = [d.lower() for d in dev_deps]
    for pkg in REQUIRED_DEV_DEPS:
        assert any(pkg in d for d in dev_lower), f"Missing dev dependency: {pkg}"


def test_pyproject_has_tool_sections():
    """Tool config sections for ruff, pytest, and mypy exist."""
    data = _load_pyproject()
    assert "ruff" in data.get("tool", {}), "Missing [tool.ruff]"
    assert "pytest" in data.get("tool", {}) or "ini_options" in str(
        data.get("tool", {}).get("pytest", {})
    ), "Missing [tool.pytest.ini_options]"
    assert "mypy" in data.get("tool", {}), "Missing [tool.mypy]"


# --- Module imports ---

MODULES = [
    "pentest",
    "pentest.agents",
    "pentest.controller",
    "pentest.database",
    "pentest.docker",
    "pentest.graphiti",
    "pentest.mcp",
    "pentest.models",
    "pentest.providers",
    "pentest.templates",
    "pentest.tools",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_all_modules_importable(module_name: str):
    """Every src/pentest submodule is importable without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("module_name", MODULES)
def test_all_modules_have_docstrings(module_name: str):
    """Each __init__.py has a non-empty module-level docstring."""
    mod = importlib.import_module(module_name)
    assert mod.__doc__ is not None, f"{module_name} has no docstring"
    assert mod.__doc__.strip(), f"{module_name} has empty docstring"


def test_package_version():
    """Installed package version matches pyproject.toml."""
    version = importlib.metadata.version("securedev-pentest")
    assert version == "0.1.0"


# --- Directory structure ---


def test_test_directories_exist():
    """All four test layer directories exist."""
    for subdir in ["unit", "integration", "agent", "e2e"]:
        path = ROOT / "tests" / subdir
        assert path.is_dir(), f"Missing test directory: tests/{subdir}/"


def test_alembic_directory_exists():
    """Alembic config and directory exist for migrations."""
    assert (ROOT / "alembic.ini").is_file(), "Missing alembic.ini"
    assert (ROOT / "alembic").is_dir(), "Missing alembic/ directory"
    assert (ROOT / "alembic" / "env.py").is_file(), "Missing alembic/env.py"
