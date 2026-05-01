"""E2E tests for Docker Sandbox Integrity."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import docker
import pytest
from sqlalchemy import text

from pentest.database.connection import close_db, get_session, init_db
from pentest.database.enums import ContainerStatus, ContainerType, FlowStatus
from pentest.database.queries.containers import get_flow_containers
from pentest.database.queries.flows import CreateFlowParams, create_flow, get_flow
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig

if TYPE_CHECKING:
    from pathlib import Path
from pentest.database.models import Base

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
).replace("@db:", "@localhost:")


@pytest.fixture(autouse=True)
def require_docker_daemon() -> None:
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon not available: {exc}")


@pytest.fixture()
async def db_session():
    """Ensure database is initialized and clean for E2E tests."""
    await init_db(TEST_DATABASE_URL, echo=False)

    # Create schema
    async with get_session() as session:
        conn = await session.connection()
        await conn.run_sync(Base.metadata.create_all)

    yield
    async with get_session() as session:
        await session.execute(text("DELETE FROM containers"))
        await session.execute(text("DELETE FROM tasks"))
        await session.execute(text("DELETE FROM flows"))
        await session.commit()
    await close_db()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_sandbox_crash_recovery_lifecycle(tmp_path: Path, db_session: object) -> None:
    """Full integrity cycle: create, work, simulate crash, cleanup, verify."""
    docker_api = docker.from_env()

    # 1. Setup - Create a real flow and container
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="E2E Integrity Test",
                model="gpt-4",
                model_provider="openai",
                language="en",
                prompts={},
            ),
        )

        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=session, config=config)

        image = "alpine:3.20"
        try:
            docker_api.images.get(image)
        except docker.errors.ImageNotFound:
            docker_api.images.pull(image)

        # Run container
        runtime_container = await client.run_container(
            name="integrity-container",
            container_type=ContainerType.PRIMARY,
            flow_id=flow.id,
            image=image,
            host_config=None,
        )
        local_id = runtime_container.local_id

        # 2. Work - Write and read a file
        content = "integrity check data"
        client.write_file(local_id, content, "check.txt")
        read_back = client.read_file(local_id, "check.txt")
        assert read_back == content

        # 3. Simulate Crash
        # We simulate a crash by marking the flow as FINISHED (orphaning the container)
        flow.status = FlowStatus.FINISHED
        await session.commit()

    # 4. Recovery - New session, restart client, run cleanup
    async with get_session() as session:
        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=session, config=config)

        # Verify container still exists in Docker before cleanup
        assert docker_api.containers.get(local_id).status == "running"

        # Execute cleanup
        await client.cleanup()
        await session.commit()

        # 5. Validation
        # Container must be gone from Docker
        with pytest.raises(docker.errors.NotFound):
            docker_api.containers.get(local_id)

        # DB status must be DELETED
        containers = await get_flow_containers(session, flow.id)
        assert containers[0].status == ContainerStatus.DELETED

        # Flow remains FINISHED (cleanup doesn't change terminal flows)
        refreshed_flow = await get_flow(session, flow.id)
        assert refreshed_flow is not None
        assert refreshed_flow.status == FlowStatus.FINISHED
