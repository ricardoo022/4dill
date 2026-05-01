"""Integration tests for DockerClient.cleanup()."""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import docker
import pytest

from pentest.database.connection import get_session
from pentest.database.enums import ContainerStatus, FlowStatus
from pentest.database.queries.containers import (
    CreateContainerParams,
    create_container,
)
from pentest.database.queries.flows import CreateFlowParams, create_flow, get_flow
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def require_docker_daemon() -> None:
    """Skip integration tests when the Docker daemon is not reachable."""
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon not available for integration test: {exc}")


@pytest.fixture
def docker_api() -> docker.DockerClient:
    """Direct docker-py client for post-condition assertions."""
    return docker.from_env()


@pytest.fixture
def test_image(docker_api: docker.DockerClient) -> str:
    """Return a local image ref."""
    image = "alpine:3.20"
    try:
        docker_api.images.get(image)
    except docker.errors.ImageNotFound:
        docker_api.images.pull(image)
    return image


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_marks_unhealthy_flow_as_failed(
    tmp_path: Path, docker_api: docker.DockerClient, db_session: object, test_image: str
) -> None:
    """DB says 'running', but Docker container is missing -> Flow becomes FAILED."""
    async with get_session() as session:
        # 1. Create a flow in RUNNING state
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="Test Unhealthy Flow",
                model="gpt-4",
                model_provider="openai",
                language="en",
                prompts={},
            ),
        )
        flow.status = FlowStatus.RUNNING
        await session.flush()

        # 2. Create a container for it with a fake local_id
        await create_container(
            session,
            CreateContainerParams(
                image=test_image,
                flow_id=flow.id,
                status=ContainerStatus.RUNNING,
                local_id="fake-id-" + uuid.uuid4().hex,
            ),
        )
        await session.commit()

    # 3. Run cleanup
    async with get_session() as session:
        client = DockerClient(db_session=session, config=DockerConfig(data_dir=str(tmp_path)))
        await client.cleanup()
        await session.commit()

    # 4. Assert Flow is now FAILED
    async with get_session() as session:
        flow_db = await get_flow(session, flow.id)
        assert flow_db is not None
        assert flow_db.status == FlowStatus.FAILED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_removes_orphaned_containers(
    tmp_path: Path, docker_api: docker.DockerClient, db_session: object, test_image: str
) -> None:
    """Flow is FINISHED, but container still exists in Docker -> Container removed."""
    async with get_session() as session:
        # 1. Create a flow in FINISHED state
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="Test Orphaned Container",
                model="gpt-4",
                model_provider="openai",
                language="en",
                prompts={},
            ),
        )
        flow.status = FlowStatus.FINISHED
        await session.flush()

        # 2. Actually start a container in Docker
        runtime = docker_api.containers.run(
            test_image, entrypoint=["tail", "-f", "/dev/null"], detach=True
        )

        # 3. Record it in DB
        container = await create_container(
            session,
            CreateContainerParams(
                image=test_image,
                flow_id=flow.id,
                status=ContainerStatus.RUNNING,
                local_id=runtime.id,
            ),
        )
        await session.commit()

    # 4. Run cleanup
    async with get_session() as session:
        client = DockerClient(db_session=session, config=DockerConfig(data_dir=str(tmp_path)))
        await client.cleanup()
        await session.commit()

    # 5. Assert container is removed from Docker
    with pytest.raises(docker.errors.NotFound):
        docker_api.containers.get(runtime.id)

    # 6. Assert DB status is DELETED
    async with get_session() as session:
        from pentest.database.models import Container as ContainerModel
        from sqlalchemy import select
        stmt = select(ContainerModel).where(ContainerModel.id == container.id)
        result = await session.execute(stmt)
        c_db = result.scalar_one()
        assert c_db.status == ContainerStatus.DELETED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_parallel_removal(
    tmp_path: Path, docker_api: docker.DockerClient, db_session: object, test_image: str
) -> None:
    """Test parallel removal of 3 orphaned containers."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="Test Parallel Cleanup",
                model="gpt-4",
                model_provider="openai",
                language="en",
                prompts={},
            ),
        )
        flow.status = FlowStatus.FAILED
        await session.flush()

        runtimes = []
        containers = []
        for i in range(3):
            runtime = docker_api.containers.run(
                test_image, entrypoint=["tail", "-f", "/dev/null"], detach=True
            )
            runtimes.append(runtime)
            c = await create_container(
                session,
                CreateContainerParams(
                    image=test_image,
                    flow_id=flow.id,
                    status=ContainerStatus.RUNNING,
                    local_id=runtime.id,
                    name=f"parallel-test-{i}-{uuid.uuid4().hex[:4]}",
                ),
            )
            containers.append(c)

        await session.commit()

    # Run cleanup
    async with get_session() as session:
        client = DockerClient(db_session=session, config=DockerConfig(data_dir=str(tmp_path)))
        await client.cleanup()
        await session.commit()

    # All must be gone
    for r in runtimes:
        with pytest.raises(docker.errors.NotFound):
            docker_api.containers.get(r.id)

    async with get_session() as session:
        from pentest.database.models import Container as ContainerModel
        from sqlalchemy import select
        for c in containers:
            stmt = select(ContainerModel).where(ContainerModel.id == c.id)
            result = await session.execute(stmt)
            c_db = result.scalar_one()
            assert c_db.status == ContainerStatus.DELETED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_idempotency(
    tmp_path: Path, docker_api: docker.DockerClient, db_session: object, test_image: str
) -> None:
    """Running cleanup twice has no side effects."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="Test Idempotency",
                model="gpt-4",
                model_provider="openai",
                language="en",
                prompts={},
            ),
        )
        flow.status = FlowStatus.FINISHED
        await session.flush()
        await session.commit()

    async with get_session() as session:
        client = DockerClient(db_session=session, config=DockerConfig(data_dir=str(tmp_path)))

        # Run 1
        await client.cleanup()
        # Run 2
        await client.cleanup()
        await session.commit()

    async with get_session() as session:
        flow_db = await get_flow(session, flow.id)
        assert flow_db is not None
        assert flow_db.status == FlowStatus.FINISHED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_finds_by_name_if_local_id_missing(
    tmp_path: Path, docker_api: docker.DockerClient, db_session: object, test_image: str
) -> None:
    """Flow FAILED, container has no local_id but exists in Docker by name -> Removed."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="Test By Name", model="m", model_provider="p", language="en", prompts={}
            ),
        )
        flow.status = FlowStatus.FAILED
        await session.flush()

        name = f"orphan-by-name-{uuid.uuid4().hex[:8]}"
        docker_api.containers.run(
            test_image, entrypoint=["tail", "-f", "/dev/null"], detach=True, name=name
        )

        container = await create_container(
            session,
            CreateContainerParams(
                image=test_image,
                flow_id=flow.id,
                status=ContainerStatus.STARTING,
                name=name,
                local_id=None,
            ),
        )
        await session.commit()

    async with get_session() as session:
        client = DockerClient(db_session=session, config=DockerConfig(data_dir=str(tmp_path)))
        await client.cleanup()
        await session.commit()

    with pytest.raises(docker.errors.NotFound):
        docker_api.containers.get(name)

    async with get_session() as session:
        from pentest.database.models import Container as ContainerModel
        from sqlalchemy import select
        stmt = select(ContainerModel).where(ContainerModel.id == container.id)
        result = await session.execute(stmt)
        c_db = result.scalar_one()
        assert c_db.status == ContainerStatus.DELETED
