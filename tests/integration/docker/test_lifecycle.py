"""Integration tests for DockerClient container lifecycle (stop and remove).

Requires the devcontainer Docker daemon to be running.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import docker
import pytest
from sqlalchemy import select

from pentest.database.connection import get_session
from pentest.database.enums import ContainerStatus, ContainerType
from pentest.database.models import Container
from pentest.database.queries.flows import CreateFlowParams, create_flow
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def require_docker_daemon() -> None:
    """Skip integration tests when the Docker daemon is not reachable."""
    try:
        client = docker.from_env()  # type: ignore
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon not available for integration test: {exc}")


@pytest.fixture
def docker_api() -> Any:
    """Direct docker-py client for post-condition assertions."""
    return docker.from_env()  # type: ignore


@pytest.fixture
def existing_local_image(docker_api: Any) -> str:
    """Return a local image ref, preferring a deterministic lightweight test image."""
    test_image = "alpine:3.20"

    try:
        docker_api.images.get(test_image)
        return test_image
    except Exception:
        pass

    try:
        docker_api.images.pull(test_image)
        return test_image
    except Exception:
        pass

    images = docker_api.images.list()
    if images:
        tagged_image = next((image for image in images if image.tags), images[0])
        return str(tagged_image.tags[0] if tagged_image.tags else tagged_image.id)

    pytest.skip(f"Could not prepare deterministic image '{test_image}' and no local images exist")


@pytest.mark.integration
async def test_stop_container_updates_db_and_stops_docker(
    tmp_path: Path,
    db_session: Any,
    docker_api: Any,
    existing_local_image: str,
) -> None:
    """stop_container stops the runtime container and sets DB status to stopped."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="test stop container",
                model="claude-3-5-sonnet",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )

        # 1. Start a container
        db_container = await client.run_container(
            name="ignored",
            container_type=ContainerType.PRIMARY,
            flow_id=flow.id,
            image=existing_local_image,
            host_config=None,
        )
        container_id = db_container.local_id
        assert container_id

        try:
            # 2. Stop the container
            await client.stop_container(container_id, db_container.id)

            # 3. Verify DB status
            stmt = select(Container).where(Container.id == db_container.id)
            result = await session.execute(stmt)
            updated_container = result.scalar_one()
            assert updated_container.status == ContainerStatus.STOPPED

            # 4. Verify Docker status
            runtime = docker_api.containers.get(container_id)
            assert runtime.status == "exited"
        finally:
            with contextlib.suppress(docker.errors.NotFound):
                docker_api.containers.get(container_id).remove(force=True)


@pytest.mark.integration
async def test_remove_container_updates_db_and_removes_docker(
    tmp_path: Path,
    db_session: Any,
    docker_api: Any,
    existing_local_image: str,
) -> None:
    """remove_container removes the runtime container and sets DB status to deleted."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="test remove container",
                model="claude-3-5-sonnet",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )

        # 1. Start a container
        db_container = await client.run_container(
            name="ignored",
            container_type=ContainerType.PRIMARY,
            flow_id=flow.id,
            image=existing_local_image,
            host_config=None,
        )
        container_id = db_container.local_id
        assert container_id

        # 2. Remove the container
        await client.remove_container(container_id, db_container.id)

        # 3. Verify DB status
        stmt = select(Container).where(Container.id == db_container.id)
        result = await session.execute(stmt)
        updated_container = result.scalar_one()
        assert updated_container.status == ContainerStatus.DELETED

        # 4. Verify Docker container is gone
        with pytest.raises(docker.errors.NotFound):
            docker_api.containers.get(container_id)


@pytest.mark.integration
async def test_lifecycle_idempotency_non_existent_container(
    tmp_path: Path,
    db_session: Any,
    caplog: pytest.LogCaptureFixture,
    existing_local_image: str,
) -> None:
    """Stopping or removing a non-existent container ID does not raise and updates DB."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="test idempotency",
                model="claude-3-5-sonnet",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )

        # Mock a DB container record that points to a non-existent Docker ID
        from pentest.database.queries.containers import CreateContainerParams, create_container

        db_container = await create_container(
            session,
            CreateContainerParams(
                type=ContainerType.PRIMARY,
                name="non-existent",
                image=existing_local_image,
                status=ContainerStatus.RUNNING,
                flow_id=flow.id,
            ),
        )

        non_existent_id = "this-id-does-not-exist"
        caplog.set_level(logging.WARNING)

        # 1. Test stop_container idempotency
        await client.stop_container(non_existent_id, db_container.id)
        # Verify DB status updated regardless of Docker error
        stmt = select(Container).where(Container.id == db_container.id)
        result = await session.execute(stmt)
        assert result.scalar_one().status == ContainerStatus.STOPPED

        # 2. Test remove_container idempotency
        await client.remove_container(non_existent_id, db_container.id)
        result = await session.execute(stmt)
        assert result.scalar_one().status == ContainerStatus.DELETED
