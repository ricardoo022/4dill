"""E2E tests for the Scanner agent using real Docker infrastructure."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from pentest.agents.scanner import run_scanner
from pentest.database.enums import ContainerStatus, ContainerType
from pentest.database.models import Container
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig
from pentest.models.hack import HackResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


@pytest.fixture
async def docker_client(tmp_path: Path) -> DockerClient:
    """Real Docker client for E2E tests."""
    mock_session = AsyncMock()
    config = DockerConfig(data_dir=str(tmp_path))
    client = DockerClient(db_session=mock_session, config=config)
    return client


async def test_run_scanner_e2e_hello_world(docker_client: DockerClient, monkeypatch):
    """
    E2E test: Prove run_scanner executes a simple task in a real container.
    Task: echo 'LusitAI' to a file and cat it.
    Expect: HackResult containing the evidence.
    """
    docker_image = "alpine:latest"
    # Ensure image is present
    import docker as docker_lib

    try:
        api_client = docker_lib.from_env()
        api_client.images.pull(docker_image)
    except Exception as e:
        pytest.skip(f"Docker not available or failed to pull image: {e}")

    # Use a random flow_id to avoid container name conflicts
    flow_id = uuid.uuid4().int & 0xFFFF

    # Mock the DB queries to avoid "awaiting coroutine" errors with AsyncMock session
    mock_container = Container(
        id=1,
        local_id="temp-id",
        name=f"test-scanner-{flow_id}",
        image=docker_image,
        status=ContainerStatus.RUNNING,
        flow_id=flow_id,
    )

    async def mock_create(*args, **kwargs):
        return mock_container

    async def mock_update(*args, **kwargs):
        if len(args) > 3:
            mock_container.local_id = args[3]
        return mock_container

    monkeypatch.setattr("pentest.docker.client.create_container", mock_create)
    monkeypatch.setattr("pentest.docker.client.update_container_status_local_id", mock_update)
    monkeypatch.setattr("pentest.docker.client.update_container_status", mock_create)
    monkeypatch.setattr("pentest.docker.client.update_container_image", mock_create)

    # Use ContainerType.PRIMARY which exists in the enum
    db_container = await docker_client.run_container(
        name="test-scanner-e2e",
        container_type=ContainerType.PRIMARY,
        flow_id=flow_id,
        image=docker_image,
        host_config=None,
    )
    container_id = db_container.local_id

    try:
        # Check for API keys
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No LLM API keys found for E2E test")

        question = (
            "Inside the container, create a file at /tmp/lusitai.txt with the content 'LusitAI'. "
            "Then, read the file to confirm its content. "
            "Finally, call hack_result with the content you read as evidence."
        )

        try:
            result = await run_scanner(
                question=question,
                docker_client=docker_client,
                container_id=container_id,
                docker_image=docker_image,
                cwd="/work",
            )
        except Exception as exc:
            if (
                "authentication_error" in str(exc).lower()
                or "invalid x-api-key" in str(exc).lower()
            ):
                pytest.skip(f"Skipping Scanner E2E due to invalid provider credentials: {exc}")
            raise

        assert isinstance(result, HackResult)
        assert "LusitAI" in result.result
        assert result.message != ""

        # Additional verification: check if file actually exists via docker_client
        content = docker_client.read_file(container_id, "/tmp/lusitai.txt")
        assert content.strip() == "LusitAI"

    finally:
        await docker_client.remove_container(container_id, db_container.id)
