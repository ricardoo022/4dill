"""US-001 to US-004: Dev Container configuration tests.

Validates devcontainer.json, docker-compose.yml, Dockerfile,
.vscode/settings.json, .env.example, and init-db.sql.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# --- Helpers ---


def _load_json(path: Path) -> dict:
    """Load a JSONC file (JSON with comments), as used by devcontainer.json."""
    import re

    text = path.read_text(encoding="utf-8")
    # Strip single-line // comments (but not inside strings)
    text = re.sub(r"(?<!:)//.*$", "", text, flags=re.MULTILINE)
    # Strip trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text, strict=False)


def _load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- US-001: devcontainer.json ---


def test_devcontainer_json_exists_and_valid():
    """devcontainer.json exists and is valid JSON(C)."""
    path = ROOT / ".devcontainer" / "devcontainer.json"
    assert path.is_file(), "Missing .devcontainer/devcontainer.json"
    data = _load_json(path)
    assert "name" in data


def test_devcontainer_python_312_image():
    """Dev container uses Python 3.12 base image."""
    dockerfile = ROOT / ".devcontainer" / "Dockerfile"
    assert dockerfile.is_file(), "Missing .devcontainer/Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "python:3.12" in content.lower() or "python:3.12" in content


def test_devcontainer_post_create_command():
    """postCreateCommand installs the project with dev extras."""
    data = _load_json(ROOT / ".devcontainer" / "devcontainer.json")
    cmd = data.get("postCreateCommand", "")
    assert "pip install" in cmd, "postCreateCommand must run pip install"
    assert ".[dev]" in cmd, "Must install dev extras"


def test_devcontainer_dockerfile_installs_claude_code_cli():
    """Dockerfile installs the Claude Code CLI globally via npm."""
    dockerfile = ROOT / ".devcontainer" / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "@anthropic-ai/claude-code" in content, "Must install Claude Code CLI"


# --- US-002: PostgreSQL + pgvector ---


def test_docker_compose_has_db_service():
    """docker-compose.yml has a db service using pgvector/pgvector:pg16."""
    path = ROOT / ".devcontainer" / "docker-compose.yml"
    assert path.is_file(), "Missing .devcontainer/docker-compose.yml"
    data = _load_yaml(path)
    services = data.get("services", {})
    assert "db" in services, "Missing 'db' service"
    assert "pgvector" in services["db"].get("image", ""), "db must use pgvector image"


def test_docker_compose_db_healthcheck():
    """DB service has a health check with pg_isready."""
    data = _load_yaml(ROOT / ".devcontainer" / "docker-compose.yml")
    db = data["services"]["db"]
    hc = db.get("healthcheck", {})
    test_cmd = " ".join(hc.get("test", []))
    assert "pg_isready" in test_cmd, "Health check must use pg_isready"


def test_docker_compose_named_volume():
    """PostgreSQL data uses a named volume for persistence."""
    data = _load_yaml(ROOT / ".devcontainer" / "docker-compose.yml")
    volumes = data.get("volumes", {})
    assert "postgres-data" in volumes, "Missing postgres-data named volume"
    db_volumes = data["services"]["db"].get("volumes", [])
    assert any("postgres-data" in str(v) for v in db_volumes), (
        "postgres-data not mounted on db service"
    )


def test_init_db_sql_creates_vector_extension():
    """init-db.sql creates the pgvector extension."""
    path = ROOT / "docker" / "init-db.sql"
    assert path.is_file(), "Missing docker/init-db.sql"
    content = path.read_text(encoding="utf-8")
    assert "CREATE EXTENSION" in content and "vector" in content


def test_env_example_exists_with_required_vars():
    """.env.example documents all required environment variables."""
    path = ROOT / ".env.example"
    assert path.is_file(), "Missing .env.example"
    content = path.read_text(encoding="utf-8")
    for var in ["DATABASE_URL", "ANTHROPIC_API_KEY", "DOCKER_INSIDE"]:
        assert var in content, f"Missing env var: {var}"


def test_env_example_documents_graphiti_vars():
    """.env.example documents the Graphiti integration variables."""
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    for var in [
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "GRAPHITI_ENABLED",
        "GRAPHITI_URL",
        "GRAPHITI_TIMEOUT",
    ]:
        assert var in content, f"Missing Graphiti env var: {var}"


# --- US-003: Docker-in-Docker ---


def test_devcontainer_has_docker_in_docker_feature():
    """devcontainer.json includes the Docker-in-Docker feature."""
    data = _load_json(ROOT / ".devcontainer" / "devcontainer.json")
    features = data.get("features", {})
    feature_keys = " ".join(features.keys())
    assert "docker-in-docker" in feature_keys, "Missing docker-in-docker feature"


def test_devcontainer_has_node_feature():
    """Dockerfile installs Node.js for the CLI tooling."""
    dockerfile = ROOT / ".devcontainer" / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "nodesource.com/setup_20.x" in content or "nodejs" in content, (
        "Dockerfile must install Node.js"
    )


def test_devcontainer_graphiti_env_and_ports():
    """devcontainer.json exposes Graphiti settings and forwarded ports."""
    data = _load_json(ROOT / ".devcontainer" / "devcontainer.json")
    env = data.get("containerEnv", {})
    assert env.get("GRAPHITI_ENABLED") == "true"
    assert env.get("GRAPHITI_URL") == "http://graphiti:8000"
    assert env.get("GRAPHITI_TIMEOUT") == "30"
    assert env.get("NEO4J_URI") == "bolt://neo4j:7687"

    forward_ports = data.get("forwardPorts", [])
    for port in [7474, 7687, 8000]:
        assert port in forward_ports, f"Port {port} must be forwarded"


def test_docker_compose_has_neo4j_service():
    """docker-compose.yml defines a Neo4j service with required ports."""
    data = _load_yaml(ROOT / ".devcontainer" / "docker-compose.yml")
    services = data.get("services", {})
    assert "neo4j" in services, "Missing 'neo4j' service"

    neo4j = services["neo4j"]
    assert neo4j.get("image") == "neo4j:community"
    ports = neo4j.get("ports", [])
    assert "7474:7474" in ports
    assert "7687:7687" in ports
    assert "healthcheck" in neo4j


def test_docker_compose_has_graphiti_service():
    """docker-compose.yml defines a Graphiti API service connected to Neo4j."""
    data = _load_yaml(ROOT / ".devcontainer" / "docker-compose.yml")
    services = data.get("services", {})
    assert "graphiti" in services, "Missing 'graphiti' service"

    graphiti = services["graphiti"]
    assert "zepai/graphiti" in graphiti.get("image", "")
    assert "8000:8000" in graphiti.get("ports", [])
    env = graphiti.get("environment", {})
    assert env.get("NEO4J_URI") == "${NEO4J_URI:-bolt://neo4j:7687}"
    assert env.get("NEO4J_USER") == "${NEO4J_USER:-neo4j}"
    assert env.get("NEO4J_PASSWORD") == "${NEO4J_PASSWORD:-changeme}"
    assert "healthcheck" in graphiti


def test_app_service_receives_graphiti_env():
    """The app service gets the Graphiti env vars for graceful toggling."""
    data = _load_yaml(ROOT / ".devcontainer" / "docker-compose.yml")
    app_env = "\n".join(data["services"]["app"].get("environment", []))
    for var in [
        "GRAPHITI_ENABLED",
        "GRAPHITI_URL",
        "GRAPHITI_TIMEOUT",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
    ]:
        assert var in app_env, f"Missing app env var: {var}"


# --- US-004: VS Code Extensions and Tooling ---


REQUIRED_EXTENSIONS = [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-python.debugpy",
    "ms-azuretools.vscode-docker",
    "github.copilot",
    "github.copilot-chat",
]


def test_devcontainer_extensions():
    """All 7 required VS Code extensions are listed."""
    data = _load_json(ROOT / ".devcontainer" / "devcontainer.json")
    extensions = data.get("customizations", {}).get("vscode", {}).get("extensions", [])
    for ext in REQUIRED_EXTENSIONS:
        assert ext in extensions, f"Missing extension: {ext}"


def test_vscode_settings_ruff_formatter():
    """.vscode/settings.json sets Ruff as the default Python formatter."""
    path = ROOT / ".vscode" / "settings.json"
    assert path.is_file(), "Missing .vscode/settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    python_settings = data.get("[python]", {})
    formatter = python_settings.get(
        "editor.defaultFormatter", data.get("editor.defaultFormatter", "")
    )
    assert formatter == "charliermarsh.ruff"


def test_vscode_settings_format_on_save():
    """Format on save is enabled."""
    data = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    # Can be at top level or in [python] scope
    fos = data.get("editor.formatOnSave") or data.get("[python]", {}).get("editor.formatOnSave")
    assert fos is True


def test_vscode_settings_pytest_enabled():
    """pytest is configured as the test framework."""
    data = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert data.get("python.testing.pytestEnabled") is True
