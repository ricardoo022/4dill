"""Integration tests for DockerClient using the real Docker daemon.

Requires the devcontainer Docker daemon to be running.
All network tests create unique networks and clean them up after.
"""

from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import docker
import pytest

from pentest.database.connection import get_session
from pentest.database.enums import ContainerStatus, ContainerType, TaskStatus
from pentest.database.queries.containers import get_flow_containers
from pentest.database.queries.flows import CreateFlowParams, create_flow
from pentest.database.queries.tasks import CreateTaskParams, create_task
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
def net_name() -> str:
    """Unique Docker network name per test to avoid cross-test pollution."""
    return f"test-pentest-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def existing_local_image(docker_api: docker.DockerClient) -> str:
    """Return a local image ref, preferring a deterministic lightweight test image."""
    test_image = "alpine:3.20"

    try:
        docker_api.images.get(test_image)
        return test_image
    except docker.errors.ImageNotFound:
        pass

    pull_error: Exception | None = None
    try:
        docker_api.images.pull(test_image)
        return test_image
    except (docker.errors.APIError, docker.errors.DockerException) as exc:
        pull_error = exc

    images = docker_api.images.list()
    if images:
        tagged_image = next((image for image in images if image.tags), images[0])
        return tagged_image.tags[0] if tagged_image.tags else tagged_image.id

    pytest.skip(
        f"Could not prepare deterministic image '{test_image}' and no local images exist: {pull_error}"
    )


@pytest.mark.integration
def test_docker_client_connects(tmp_path: Path) -> None:
    """DockerClient connects to the real Docker daemon and initialises successfully."""
    config = DockerConfig(data_dir=str(tmp_path))
    client = DockerClient(db_session=MagicMock(), config=config)
    assert client.get_default_image() == "debian:latest"


@pytest.mark.integration
def test_get_default_image_returns_configured_value(tmp_path: Path) -> None:
    """get_default_image() returns whatever docker_default_image is set to."""
    config = DockerConfig(data_dir=str(tmp_path), docker_default_image="alpine:latest")
    client = DockerClient(db_session=MagicMock(), config=config)
    assert client.get_default_image() == "alpine:latest"


@pytest.mark.integration
def test_data_dir_created_on_disk(tmp_path: Path) -> None:
    """DockerClient creates a nested data_dir on disk during initialisation."""
    data_dir = tmp_path / "subdir" / "data"
    config = DockerConfig(data_dir=str(data_dir))
    DockerClient(db_session=MagicMock(), config=config)
    assert data_dir.exists()
    assert data_dir.is_dir()


@pytest.mark.integration
def test_network_created_if_missing(
    tmp_path: Path, net_name: str, docker_api: docker.DockerClient
) -> None:
    """A bridge network is actually created in Docker when it doesn't exist yet."""
    config = DockerConfig(data_dir=str(tmp_path), docker_network=net_name)
    try:
        DockerClient(db_session=MagicMock(), config=config)
        network = docker_api.networks.get(net_name)
        assert network.attrs["Driver"] == "bridge"
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.networks.get(net_name).remove()


@pytest.mark.integration
def test_network_not_recreated_if_exists(
    tmp_path: Path, net_name: str, docker_api: docker.DockerClient
) -> None:
    """Initialising DockerClient twice with the same network name is idempotent."""
    config = DockerConfig(data_dir=str(tmp_path), docker_network=net_name)
    try:
        DockerClient(db_session=MagicMock(), config=config)
        first_id = docker_api.networks.get(net_name).id

        DockerClient(db_session=MagicMock(), config=config)
        second_id = docker_api.networks.get(net_name).id

        assert first_id == second_id, "Network should not be recreated"
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.networks.get(net_name).remove()


@pytest.mark.integration
def test_network_skipped_for_host_mode(tmp_path: Path, docker_api: docker.DockerClient) -> None:
    """No new network is created when docker_network is 'host'."""
    networks_before = {n.name for n in docker_api.networks.list()}
    config = DockerConfig(data_dir=str(tmp_path), docker_network="host")
    DockerClient(db_session=MagicMock(), config=config)
    networks_after = {n.name for n in docker_api.networks.list()}
    new_networks = networks_after - networks_before
    pentest_networks = {n for n in new_networks if n.startswith("test-pentest-")}
    assert not pentest_networks


@pytest.mark.integration
def test_ensure_image_success_with_real_daemon(tmp_path: Path, existing_local_image: str) -> None:
    """ensure_image returns the requested image when it exists locally."""
    config = DockerConfig(data_dir=str(tmp_path))
    client = DockerClient(db_session=MagicMock(), config=config)

    resolved = client.ensure_image(existing_local_image)

    assert resolved == existing_local_image


@pytest.mark.integration
def test_ensure_image_cache_hit_does_not_pull(tmp_path: Path, existing_local_image: str) -> None:
    """ensure_image skips pull when the image is already present in local cache."""
    config = DockerConfig(data_dir=str(tmp_path))
    client = DockerClient(db_session=MagicMock(), config=config)
    with pytest.MonkeyPatch.context() as monkeypatch:
        pull_mock = MagicMock(side_effect=AssertionError("pull must not be called"))
        monkeypatch.setattr(client._client.images, "pull", pull_mock)

        resolved = client.ensure_image(existing_local_image)

    assert resolved == existing_local_image
    pull_mock.assert_not_called()


@pytest.mark.integration
@patch("pentest.docker.client.update_container_status")
@patch("pentest.docker.client.update_container_image")
@patch("pentest.docker.client.update_container_status_local_id", new_callable=AsyncMock)
@patch("pentest.docker.client.create_container", new_callable=AsyncMock)
async def test_run_container_bridge_mode_starts_container_with_expected_config(
    mock_create_container: AsyncMock,
    mock_update_status_local_id: AsyncMock,
    mock_update_image: MagicMock,
    mock_update_status: MagicMock,
    tmp_path: Path,
    docker_api: docker.DockerClient,
    existing_local_image: str,
) -> None:
    config = DockerConfig(
        data_dir=str(tmp_path),
        docker_network="",
        docker_inside=False,
        docker_default_image=existing_local_image,
    )
    client = DockerClient(db_session=MagicMock(), config=config)
    mock_create_container.return_value = SimpleNamespace(id=101)

    async def _return_updated(
        _db: object, cid: int, status: object, local_id: str
    ) -> SimpleNamespace:
        return SimpleNamespace(id=cid, status=status, local_id=local_id)

    mock_update_status_local_id.side_effect = _return_updated

    result = await client.run_container(
        name="ignored",
        container_type=ContainerType.PRIMARY,
        flow_id=1,
        image=existing_local_image,
        host_config=None,
    )

    try:
        runtime = docker_api.containers.get(result.local_id)
        runtime.reload()
        attrs = runtime.attrs
        assert attrs["Config"]["WorkingDir"] == "/work"
        assert attrs["Config"]["Hostname"] == DockerClient._crc32_hostname("pentestai-terminal-1")
        assert attrs["HostConfig"]["RestartPolicy"]["Name"] == "on-failure"
        assert attrs["HostConfig"]["RestartPolicy"]["MaximumRetryCount"] == 5
        assert attrs["HostConfig"]["LogConfig"]["Type"] == "json-file"
        assert "28002/tcp" in (attrs["HostConfig"].get("PortBindings") or {})
        assert "28003/tcp" in (attrs["HostConfig"].get("PortBindings") or {})
        assert any(m["Destination"] == "/work" for m in attrs.get("Mounts", []))

        runtime.exec_run("sh -lc 'echo ready > /work/test.txt'")
        host_file = tmp_path / "flow-1" / "test.txt"
        assert host_file.exists()
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.containers.get(result.local_id).remove(force=True)

    assert mock_update_image.await_count == 0
    assert mock_update_status.await_count == 0


@pytest.mark.integration
@patch("pentest.docker.client.update_container_status")
@patch("pentest.docker.client.update_container_image")
@patch("pentest.docker.client.update_container_status_local_id", new_callable=AsyncMock)
@patch("pentest.docker.client.create_container", new_callable=AsyncMock)
async def test_run_container_host_mode_uses_host_network_without_port_bindings(
    mock_create_container: AsyncMock,
    mock_update_status_local_id: AsyncMock,
    _mock_update_image: MagicMock,
    _mock_update_status: MagicMock,
    tmp_path: Path,
    docker_api: docker.DockerClient,
    existing_local_image: str,
) -> None:
    config = DockerConfig(
        data_dir=str(tmp_path),
        docker_network="host",
        docker_inside=False,
        docker_default_image=existing_local_image,
    )
    client = DockerClient(db_session=MagicMock(), config=config)
    mock_create_container.return_value = SimpleNamespace(id=202)

    async def _return_updated(
        _db: object, cid: int, status: object, local_id: str
    ) -> SimpleNamespace:
        return SimpleNamespace(id=cid, status=status, local_id=local_id)

    mock_update_status_local_id.side_effect = _return_updated

    result = await client.run_container(
        name="ignored",
        container_type=ContainerType.PRIMARY,
        flow_id=2,
        image=existing_local_image,
        host_config={"ports": {"9999/tcp": ("0.0.0.0", 9999)}},
    )

    try:
        runtime = docker_api.containers.get(result.local_id)
        runtime.reload()
        attrs = runtime.attrs
        assert attrs["HostConfig"]["NetworkMode"] == "host"
        assert not attrs["HostConfig"].get("PortBindings")
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.containers.get(result.local_id).remove(force=True)


@pytest.mark.integration
async def test_run_container_persists_db_status_running_with_local_id(
    tmp_path: Path,
    docker_api: docker.DockerClient,
    db_session: object,
    existing_local_image: str,
) -> None:
    """🔁 run_container persists DB state and Docker id, then can be queried back by flow."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="scan https://juice-shop.local",
                model="claude-sonnet-4-6",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        # Keep data realistic for runtime lifecycle; task presence mirrors real flow context.
        await create_task(
            session,
            CreateTaskParams(
                status=TaskStatus.CREATED,
                title="Docker bootstrap",
                input="Create isolated scan runtime",
                flow_id=flow.id,
            ),
        )

        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )
        container_name = f"pentestai-terminal-{flow.id}"
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.containers.get(container_name).remove(force=True)

        result = await client.run_container(
            name="ignored",
            container_type=ContainerType.PRIMARY,
            flow_id=flow.id,
            image=existing_local_image,
            host_config=None,
        )

        try:
            rows = await get_flow_containers(session, flow.id)
            assert len(rows) == 1
            row = rows[0]
            assert result.id == row.id
            assert row.status == ContainerStatus.RUNNING
            assert row.local_id
            runtime = docker_api.containers.get(row.local_id)
            runtime.reload()
            assert runtime.status == "running"
        finally:
            if result.local_id:
                with contextlib.suppress(docker.errors.NotFound):
                    docker_api.containers.get(result.local_id).remove(force=True)


@pytest.mark.integration
async def test_run_container_creation_failure_retries_with_default_image(
    tmp_path: Path,
    docker_api: docker.DockerClient,
    db_session: object,
    existing_local_image: str,
) -> None:
    """Creation with custom image failure retries once and succeeds with default image."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="scan https://target.internal",
                model="claude-sonnet-4-6",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )
        from docker.models.containers import ContainerCollection

        original_run = ContainerCollection.run

        def run_side_effect(self: object, image: str, *args: object, **kwargs: object) -> object:
            if image == "custom/image:broken":
                raise docker.errors.APIError("simulated creation failure for custom image")
            return original_run(self, image, *args, **kwargs)

        container_name = f"pentestai-terminal-{flow.id}"
        with contextlib.suppress(docker.errors.NotFound):
            docker_api.containers.get(container_name).remove(force=True)

        with (
            patch.object(
                client, "ensure_image", side_effect=["custom/image:broken", existing_local_image]
            ),
            patch("docker.models.containers.ContainerCollection.run", new=run_side_effect),
        ):
            result = await client.run_container(
                name="ignored",
                container_type=ContainerType.PRIMARY,
                flow_id=flow.id,
                image="custom/image:broken",
                host_config=None,
            )

        try:
            rows = await get_flow_containers(session, flow.id)
            assert len(rows) == 1
            assert rows[0].image == existing_local_image.lower()
            assert rows[0].status == ContainerStatus.RUNNING
            assert rows[0].local_id == result.local_id
        finally:
            if result.local_id:
                with contextlib.suppress(docker.errors.NotFound):
                    docker_api.containers.get(result.local_id).remove(force=True)


@pytest.mark.integration
async def test_run_container_invalid_image_and_default_failure_marks_failed(
    tmp_path: Path,
    db_session: object,
    existing_local_image: str,
) -> None:
    """Failure path: when requested and default images fail at creation, DB status becomes failed."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(
                title="scan https://broken.registry.local",
                model="claude-sonnet-4-6",
                model_provider="anthropic",
                language="en",
                prompts={},
            ),
        )
        client = DockerClient(
            db_session=session,
            config=DockerConfig(data_dir=str(tmp_path), docker_default_image=existing_local_image),
        )

        with (
            patch.object(
                client, "ensure_image", side_effect=["custom/image:missing", existing_local_image]
            ),
            patch(
                "docker.models.containers.ContainerCollection.run",
                side_effect=docker.errors.APIError("simulated creation failure"),
            ),
            pytest.raises(docker.errors.APIError),
        ):
            await client.run_container(
                name="ignored",
                container_type=ContainerType.PRIMARY,
                flow_id=flow.id,
                image="custom/image:missing",
                host_config=None,
            )

        rows = await get_flow_containers(session, flow.id)
        assert len(rows) == 1
        assert rows[0].status == ContainerStatus.FAILED
        assert rows[0].local_id is None


# ---------------------------------------------------------------------------
# US-015: is_container_running / exec_command integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_is_container_running_true_for_running_container(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    assert file_client.is_container_running(running_container.id) is True


@pytest.mark.integration
def test_is_container_running_false_for_stopped_container(
    file_client: DockerClient,
    docker_api: docker.DockerClient,
    existing_local_image: str,
) -> None:
    container = docker_api.containers.run(
        existing_local_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"test-stopped-{uuid.uuid4().hex[:8]}",
    )
    try:
        container.stop()
        assert file_client.is_container_running(container.id) is False
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            container.remove(force=True)


@pytest.mark.integration
def test_exec_command_basic_and_stderr_capture(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    ok_output = file_client.exec_command(running_container.id, "echo hello", timeout=5)
    assert "hello" in ok_output

    err_output = file_client.exec_command(running_container.id, "ls /nonexistent", timeout=5)
    assert "No such file" in err_output or "cannot access" in err_output


@pytest.mark.integration
def test_exec_command_timeout_and_detach_mode(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    timeout_output = file_client.exec_command(running_container.id, "sleep 10", timeout=2)
    assert "Command timed out after 2s" in timeout_output

    detach_output = file_client.exec_command(
        running_container.id,
        "sleep 60",
        timeout=5,
        detach=True,
    )
    assert detach_output == "Command started in background"


@pytest.mark.integration
def test_exec_command_workdir_defaults_and_custom(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    default_cwd = file_client.exec_command(running_container.id, "pwd", timeout=5)
    assert default_cwd.strip() == "/work"

    custom_cwd = file_client.exec_command(running_container.id, "pwd", cwd="/tmp", timeout=5)
    assert custom_cwd.strip() == "/tmp"


@pytest.mark.integration
def test_exec_command_empty_output_and_invalid_utf8(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    empty_output = file_client.exec_command(running_container.id, "true", timeout=5)
    assert empty_output == "Command completed successfully with exit code 0"

    invalid_utf8 = file_client.exec_command(
        running_container.id,
        "printf 'ok\\377\\376bad'",
        timeout=5,
    )
    assert "ok" in invalid_utf8
    assert "bad" in invalid_utf8
    assert "�" in invalid_utf8


@pytest.mark.integration
def test_exec_command_timeout_output_is_truncated_to_500_chars(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    long_running_output = file_client.exec_command(
        running_container.id,
        "yes A | tr -d '\\n' | head -c 700; sleep 10",
        timeout=1,
    )

    rendered_output, timeout_hint = long_running_output.split("\nCommand timed out after 1s", maxsplit=1)
    assert rendered_output.endswith("...")
    assert len(rendered_output[:-3]) == 500
    assert set(rendered_output[:-3]) == {"A"}
    assert "Try detached mode for long-running commands." in timeout_hint


@pytest.mark.integration
def test_exec_command_timeout_uses_max_timeout_clamp_in_hint(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    monotonic_values = [0.0, 1301.0, 1302.0]

    def _fake_monotonic() -> float:
        if monotonic_values:
            return monotonic_values.pop(0)
        return 1302.0

    with patch("pentest.docker.client.time", SimpleNamespace(monotonic=_fake_monotonic)):
        output = file_client.exec_command(
            running_container.id,
            "sleep 60",
            timeout=9999,
        )

    assert "Command timed out after 1200s" in output


# ---------------------------------------------------------------------------
# US-016: read_file / write_file integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def running_container(
    tmp_path: Path, docker_api: docker.DockerClient, existing_local_image: str
) -> docker.models.containers.Container:
    """Start a lightweight container for file operation tests, remove after."""
    container = docker_api.containers.run(
        existing_local_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"test-file-ops-{uuid.uuid4().hex[:8]}",
    )
    container.exec_run(["sh", "-c", "mkdir -p /work"])
    yield container
    with contextlib.suppress(docker.errors.NotFound):
        container.remove(force=True)


@pytest.fixture
def file_client(tmp_path: Path) -> DockerClient:
    """DockerClient instance with small size limits for testing."""
    config = DockerConfig(
        data_dir=str(tmp_path),
        max_read_file_size=10 * 1024 * 1024,
        max_write_file_size=5 * 1024 * 1024,
    )
    return DockerClient(db_session=MagicMock(), config=config)


@pytest.mark.integration
def test_write_and_read_file_roundtrip(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    """Write a file and read it back; content must match exactly."""
    content = "hello from US-016\nline two"
    file_client.write_file(running_container.id, content, "/work/test.txt")
    result = file_client.read_file(running_container.id, "/work/test.txt")
    assert result == content


@pytest.mark.integration
def test_write_script_exec_and_read_output(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    """Write a Python script, execute it, and read its output file."""
    script_content = (
        'with open("/work/out.txt", "w", encoding="utf-8") as f:\n    f.write("success")\n'
    )
    file_client.write_file(running_container.id, script_content, "/work/script.py")

    exit_code, output = running_container.exec_run(["python3", "/work/script.py"])
    if exit_code != 0:
        pytest.skip(
            f"python3 not available in test image: {output.decode('utf-8', errors='replace')}"
        )

    result = file_client.read_file(running_container.id, "/work/out.txt")
    assert result.strip() == "success"


@pytest.mark.integration
def test_read_nonexistent_file_raises_file_not_found(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    with pytest.raises(FileNotFoundError):
        file_client.read_file(running_container.id, "/work/does_not_exist.txt")


@pytest.mark.integration
def test_write_nested_path_creates_parent_directories(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    file_client.write_file(running_container.id, "nested", "/work/dir1/dir2/file.txt")
    result = file_client.read_file(running_container.id, "/work/dir1/dir2/file.txt")
    assert result == "nested"


@pytest.mark.integration
def test_read_file_with_invalid_utf8_returns_replacement_chars(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    """Inject raw bytes with invalid UTF-8 sequence via exec; read_file must not crash."""
    # Ensure /work exists as we are bypassing write_file which normally handles it.
    running_container.exec_run(
        ["sh", "-c", "mkdir -p /work && printf 'ok\\xff\\xfebad' > /work/binary.bin"]
    )
    result = file_client.read_file(running_container.id, "/work/binary.bin")
    assert "ok" in result
    assert "bad" in result
    assert "�" in result


@pytest.mark.integration
def test_write_large_file_rejected_with_size_error(
    tmp_path: Path,
    running_container: docker.models.containers.Container,
) -> None:
    """write_file rejects content that exceeds max_write_file_size."""
    config = DockerConfig(data_dir=str(tmp_path), max_write_file_size=1024)
    client = DockerClient(db_session=MagicMock(), config=config)
    with pytest.raises(ValueError, match="exceeds maximum write size"):
        client.write_file(running_container.id, "x" * 2000, "/work/big.txt")


@pytest.mark.integration
def test_written_file_is_readable_and_executable(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    file_client.write_file(running_container.id, "#!/bin/sh\necho hi\n", "/work/run.sh")
    exit_code, output = running_container.exec_run(["/work/run.sh"])
    assert exit_code == 0
    assert b"hi" in output


@pytest.mark.integration
def test_write_empty_content_creates_empty_file(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    file_client.write_file(running_container.id, "", "/work/empty.txt")
    result = file_client.read_file(running_container.id, "/work/empty.txt")
    assert result == ""


@pytest.mark.integration
def test_multiple_files_no_cross_contamination(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    file_client.write_file(running_container.id, "content_A", "/work/a.txt")
    file_client.write_file(running_container.id, "content_B", "/work/b.txt")
    assert file_client.read_file(running_container.id, "/work/a.txt") == "content_A"
    assert file_client.read_file(running_container.id, "/work/b.txt") == "content_B"


@pytest.mark.integration
def test_read_file_rejects_oversized_file_in_real_container(
    tmp_path: Path,
    running_container: docker.models.containers.Container,
) -> None:
    """🔁 read_file raises ValueError when a real file inside the container exceeds max_read_file_size.

    Covers the read-side size limit which is only exercised against a mock in unit tests.
    Creates a 2 KB file via dd inside the running container, then attempts to read it
    with a DockerClient configured to a 512-byte limit.
    """
    running_container.exec_run(
        ["sh", "-c", "dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\\0' 'x' > /tmp/big.txt"]
    )
    config = DockerConfig(data_dir=str(tmp_path), max_read_file_size=512)
    client = DockerClient(db_session=MagicMock(), config=config)
    with pytest.raises(ValueError, match="exceeds maximum read size"):
        client.read_file(running_container.id, "/tmp/big.txt")


@pytest.mark.integration
def test_pentest_recon_script_write_exec_read_output(
    file_client: DockerClient,
    running_container: docker.models.containers.Container,
) -> None:
    """🔁 Write a sh reconnaissance script, exec it, read back structured JSON findings.

    Simulates the Scanner agent file workflow with realistic pentest domain data:
    the script targets 127.0.0.1 and writes a findings JSON referencing CVE-2021-44228
    (Log4Shell) as a representative scan artifact format.
    """
    import json

    script = (
        "#!/bin/sh\n"
        "HOST='127.0.0.1'\n"
        "TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo '1970-01-01T00:00:00Z')\n"
        'printf \'{"host":"%s","timestamp":"%s","scanner":"pentest-recon-v1",'
        '"cve_reference":"CVE-2021-44228"}\' "$HOST" "$TS" > /work/findings.json\n'
    )
    file_client.write_file(running_container.id, script, "/work/recon.sh")
    exit_code, _ = running_container.exec_run(["sh", "/work/recon.sh"])
    assert exit_code == 0

    raw = file_client.read_file(running_container.id, "/work/findings.json")
    findings = json.loads(raw.strip())
    assert findings["host"] == "127.0.0.1"
    assert "timestamp" in findings
    assert findings["scanner"] == "pentest-recon-v1"
    assert findings["cve_reference"] == "CVE-2021-44228"
