"""Unit tests for DockerClient — only tests that require mocking.

Tests that can use a real Docker daemon live in tests/integration/docker/test_client.py.
"""

import concurrent.futures
import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import docker.errors
import pytest
from pydantic import ValidationError

from pentest.database.enums import ContainerStatus, ContainerType
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig
from pentest.docker.exceptions import DockerConnectionError, DockerImageError


@patch("pentest.docker.client.docker.from_env")
def test_init_raises_docker_connection_error(mock_from_env: MagicMock) -> None:
    """DockerClient raises DockerConnectionError when the daemon is unreachable.

    Cannot be tested with a real daemon — we need to simulate a connection failure.
    """
    mock_from_env.side_effect = docker.errors.DockerException("Connection refused")
    config = DockerConfig(data_dir="/tmp/test-docker-error")
    db_session = MagicMock()

    with pytest.raises(DockerConnectionError, match="Connection refused") as exc_info:
        DockerClient(db_session=db_session, config=config)
    assert exc_info.value.socket == config.docker_socket


def test_config_empty_data_dir_raises_validation_error() -> None:
    """DockerConfig rejects an empty data_dir with a Pydantic ValidationError.

    Pure model validation — no Docker daemon involved.
    """
    with pytest.raises(ValidationError, match="data_dir cannot be empty"):
        DockerConfig(data_dir="")


@pytest.fixture
def docker_client_for_images() -> DockerClient:
    client = DockerClient.__new__(DockerClient)
    client._client = MagicMock()
    client._def_image = "debian:latest"
    client._pull_timeout = 300
    return client


def test_ensure_image_cache_hit_skips_pull(docker_client_for_images: DockerClient) -> None:
    docker_client_for_images._client.images.get.return_value = MagicMock()

    result = docker_client_for_images.ensure_image("alpine:latest")

    assert result == "alpine:latest"
    docker_client_for_images._client.images.get.assert_called_once_with("alpine:latest")
    docker_client_for_images._client.images.pull.assert_not_called()


def test_ensure_image_pull_success_when_missing(docker_client_for_images: DockerClient) -> None:
    docker_client_for_images._client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    docker_client_for_images._pull_image = MagicMock(return_value=None)

    result = docker_client_for_images.ensure_image("alpine:latest")

    assert result == "alpine:latest"
    docker_client_for_images._pull_image.assert_called_once_with("alpine:latest")


def test_ensure_image_fallback_success_when_requested_pull_fails(
    docker_client_for_images: DockerClient,
) -> None:
    docker_client_for_images._client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    docker_client_for_images._pull_image = MagicMock(
        side_effect=[docker.errors.APIError("pull failed"), None]
    )

    result = docker_client_for_images.ensure_image("does-not-exist:v1")

    assert result == "debian:latest"
    assert docker_client_for_images._pull_image.call_args_list == [
        call("does-not-exist:v1"),
        call("debian:latest"),
    ]


def test_ensure_image_raises_when_requested_and_fallback_pull_fail(
    docker_client_for_images: DockerClient,
) -> None:
    docker_client_for_images._client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    docker_client_for_images._pull_image = MagicMock(
        side_effect=[
            docker.errors.ImageNotFound("requested not found"),
            docker.errors.APIError("fallback failed"),
        ]
    )

    with pytest.raises(DockerImageError, match="Failed to pull requested image"):
        docker_client_for_images.ensure_image("does-not-exist:v1")

    assert docker_client_for_images._pull_image.call_count == 2


def test_ensure_image_timeout_attempts_fallback(docker_client_for_images: DockerClient) -> None:
    docker_client_for_images._client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    docker_client_for_images._pull_image = MagicMock(
        side_effect=[concurrent.futures.TimeoutError(), None]
    )

    result = docker_client_for_images.ensure_image("slow:image")

    assert result == "debian:latest"
    assert docker_client_for_images._pull_image.call_args_list == [
        call("slow:image"),
        call("debian:latest"),
    ]


@patch("pentest.docker.client.logger")
def test_ensure_image_fallback_logs_warning_with_reason(
    mock_logger: MagicMock, docker_client_for_images: DockerClient
) -> None:
    """Fallback path logs warning with requested image and error reason."""
    docker_client_for_images._client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    docker_client_for_images._pull_image = MagicMock(
        side_effect=[docker.errors.APIError("auth denied"), None]
    )

    resolved = docker_client_for_images.ensure_image("nonexistent/image:v99")

    assert resolved == "debian:latest"
    mock_logger.warning.assert_called_once()
    args, kwargs = mock_logger.warning.call_args
    assert args[0] == "docker_image_pull_failed_using_fallback"
    assert kwargs["extra"]["requested_image"] == "nonexistent/image:v99"
    assert kwargs["extra"]["fallback_image"] == "debian:latest"
    assert "auth denied" in kwargs["extra"]["error"]


@pytest.fixture
def docker_client_for_run_container(tmp_path: Path) -> DockerClient:
    client = DockerClient.__new__(DockerClient)
    client._client = MagicMock()
    client._db = MagicMock()
    client._inside = False
    client._network = "bridge-net"
    client._public_ip = "0.0.0.0"
    client._def_image = "debian:latest"
    client._data_dir = str(tmp_path / "data")
    client._host_dir = ""
    client._socket = "/var/run/docker.sock"
    return client


@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.create_container")
async def test_run_container_uses_canonical_name_and_bridge_ports(
    mock_create_container: MagicMock,
    mock_update_status_local_id: MagicMock,
    docker_client_for_run_container: DockerClient,
) -> None:
    db_container = MagicMock(id=11)
    mock_create_container.return_value = db_container
    runtime_container = MagicMock(id="cid-123")
    docker_client_for_run_container._client.containers.run.return_value = runtime_container
    docker_client_for_run_container.ensure_image = MagicMock(return_value="kalilinux/kali-rolling")
    updated = MagicMock(status=ContainerStatus.RUNNING, local_id="cid-123")
    mock_update_status_local_id.return_value = updated

    result = await docker_client_for_run_container.run_container(
        name="ignored-by-design",
        container_type=ContainerType.PRIMARY,
        flow_id=1,
        image="kalilinux/kali-rolling",
        host_config=None,
    )

    assert result is updated
    docker_client_for_run_container.ensure_image.assert_called_once_with("kalilinux/kali-rolling")
    called_image, called_kwargs = docker_client_for_run_container._client.containers.run.call_args
    assert called_image[0] == "kalilinux/kali-rolling"
    assert called_kwargs["name"] == "pentestai-terminal-1"
    assert called_kwargs["hostname"] == DockerClient._crc32_hostname("pentestai-terminal-1")
    assert called_kwargs["working_dir"] == "/work"
    assert called_kwargs["ports"] == {
        "28002/tcp": ("0.0.0.0", 28002),
        "28003/tcp": ("0.0.0.0", 28003),
    }
    assert called_kwargs["network"] == "bridge-net"
    assert "network_mode" not in called_kwargs


@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.create_container")
async def test_run_container_host_mode_disables_ports(
    mock_create_container: MagicMock,
    mock_update_status_local_id: MagicMock,
    docker_client_for_run_container: DockerClient,
) -> None:
    docker_client_for_run_container._network = "host"
    docker_client_for_run_container.ensure_image = MagicMock(return_value="alpine:latest")
    mock_create_container.return_value = MagicMock(id=22)
    docker_client_for_run_container._client.containers.run.return_value = MagicMock(id="cid-234")
    mock_update_status_local_id.return_value = MagicMock(id=22)

    await docker_client_for_run_container.run_container(
        name="ignored",
        container_type=ContainerType.PRIMARY,
        flow_id=7,
        image="alpine:latest",
        host_config={"ports": {"1/tcp": ("0.0.0.0", 1)}},
    )
    _, called_kwargs = docker_client_for_run_container._client.containers.run.call_args
    assert called_kwargs["network_mode"] == "host"
    assert "ports" not in called_kwargs
    assert "network" not in called_kwargs


@patch("pentest.docker.client.update_container_status")
@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.update_container_image")
@patch("pentest.docker.client.create_container")
async def test_run_container_retries_with_default_image_on_creation_failure(
    mock_create_container: MagicMock,
    mock_update_image: MagicMock,
    mock_update_status_local_id: MagicMock,
    mock_update_status: MagicMock,
    docker_client_for_run_container: DockerClient,
) -> None:
    mock_create_container.return_value = MagicMock(id=33)
    docker_client_for_run_container._client.containers.run.side_effect = [
        docker.errors.APIError("create failed"),
        MagicMock(id="cid-999"),
    ]
    docker_client_for_run_container.ensure_image = MagicMock(
        side_effect=["custom:image", "debian:latest"]
    )
    mock_update_status_local_id.return_value = MagicMock(id=33)

    await docker_client_for_run_container.run_container(
        name="ignored",
        container_type=ContainerType.PRIMARY,
        flow_id=42,
        image="custom:image",
        host_config=None,
    )
    assert docker_client_for_run_container._client.containers.run.call_args_list[0][0][0] == (
        "custom:image"
    )
    assert docker_client_for_run_container._client.containers.run.call_args_list[1][0][0] == (
        "debian:latest"
    )
    mock_update_image.assert_called_once()
    mock_update_status.assert_not_called()


# ---------------------------------------------------------------------------
# read_file / write_file unit tests
# ---------------------------------------------------------------------------


def _make_tar(filename: str, content: bytes) -> bytes:
    """Build an in-memory tar archive with a single file entry."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@pytest.fixture
def docker_client_for_files() -> DockerClient:
    client = DockerClient.__new__(DockerClient)
    client._client = MagicMock()
    client._max_read_size = 10 * 1024 * 1024
    client._max_write_size = 5 * 1024 * 1024
    return client


def _running_container(docker_client_for_files: DockerClient) -> MagicMock:
    container = MagicMock()
    container.status = "running"
    docker_client_for_files._client.containers.get.return_value = container
    return container


def test_read_file_returns_utf8_content(docker_client_for_files: DockerClient) -> None:
    container = _running_container(docker_client_for_files)
    tar_bytes = _make_tar("hello.txt", b"hello world")
    container.get_archive.return_value = ([tar_bytes], MagicMock())

    result = docker_client_for_files.read_file("cid-1", "/work/hello.txt")

    assert result == "hello world"
    container.get_archive.assert_called_once_with("/work/hello.txt")


def test_read_file_prepends_work_prefix_for_relative_path(
    docker_client_for_files: DockerClient,
) -> None:
    container = _running_container(docker_client_for_files)
    tar_bytes = _make_tar("script.py", b"print('ok')")
    container.get_archive.return_value = ([tar_bytes], MagicMock())

    docker_client_for_files.read_file("cid-1", "script.py")

    container.get_archive.assert_called_once_with("/work/script.py")


def test_read_file_replaces_invalid_utf8_bytes(docker_client_for_files: DockerClient) -> None:
    container = _running_container(docker_client_for_files)
    raw = b"ok\xff\xfebad"
    tar_bytes = _make_tar("data.bin", raw)
    container.get_archive.return_value = ([tar_bytes], MagicMock())

    result = docker_client_for_files.read_file("cid-1", "/work/data.bin")

    assert "�" in result
    assert "ok" in result
    assert "bad" in result


def test_read_file_raises_file_not_found_when_container_missing(
    docker_client_for_files: DockerClient,
) -> None:
    docker_client_for_files._client.containers.get.side_effect = docker.errors.NotFound("gone")

    with pytest.raises(FileNotFoundError, match="Container not found"):
        docker_client_for_files.read_file("no-such-container", "/work/file.txt")


def test_read_file_raises_file_not_found_on_api_error(
    docker_client_for_files: DockerClient,
) -> None:
    container = _running_container(docker_client_for_files)
    container.get_archive.side_effect = docker.errors.APIError("No such file or directory")

    with pytest.raises(FileNotFoundError, match="File not found in container"):
        docker_client_for_files.read_file("cid-1", "/work/missing.txt")


def test_read_file_raises_when_container_not_running(
    docker_client_for_files: DockerClient,
) -> None:
    container = MagicMock()
    container.status = "exited"
    docker_client_for_files._client.containers.get.return_value = container

    with pytest.raises(RuntimeError, match="not running"):
        docker_client_for_files.read_file("cid-1", "/work/file.txt")


def test_read_file_raises_value_error_when_exceeds_size_limit(
    docker_client_for_files: DockerClient,
) -> None:
    docker_client_for_files._max_read_size = 5
    container = _running_container(docker_client_for_files)
    tar_bytes = _make_tar("big.txt", b"x" * 100)
    container.get_archive.return_value = ([tar_bytes], MagicMock())

    with pytest.raises(ValueError, match="exceeds maximum read size"):
        docker_client_for_files.read_file("cid-1", "/work/big.txt")


def test_write_file_puts_tar_to_parent_dir(docker_client_for_files: DockerClient) -> None:
    container = _running_container(docker_client_for_files)

    result = docker_client_for_files.write_file("cid-1", "print('hi')", "/work/script.py")

    assert result == "File written to /work/script.py"
    container.exec_run.assert_called_once_with(["mkdir", "-p", "/work"])
    container.put_archive.assert_called_once()
    dest_dir, tar_data = container.put_archive.call_args[0]
    assert dest_dir == "/work"
    with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
        members = tar.getmembers()
        assert len(members) == 1
        assert members[0].name == "script.py"
        assert tar.extractfile(members[0]).read() == b"print('hi')"


def test_write_file_prepends_work_prefix_for_relative_path(
    docker_client_for_files: DockerClient,
) -> None:
    container = _running_container(docker_client_for_files)

    docker_client_for_files.write_file("cid-1", "data", "out.txt")

    dest_dir, _ = container.put_archive.call_args[0]
    assert dest_dir == "/work"


def test_write_file_creates_nested_parent_dirs(docker_client_for_files: DockerClient) -> None:
    container = _running_container(docker_client_for_files)

    docker_client_for_files.write_file("cid-1", "data", "/work/dir1/dir2/file.txt")

    container.exec_run.assert_called_once_with(["mkdir", "-p", "/work/dir1/dir2"])
    dest_dir, _ = container.put_archive.call_args[0]
    assert dest_dir == "/work/dir1/dir2"


def test_write_file_raises_value_error_when_content_exceeds_size_limit(
    docker_client_for_files: DockerClient,
) -> None:
    docker_client_for_files._max_write_size = 10
    container = _running_container(docker_client_for_files)

    with pytest.raises(ValueError, match="exceeds maximum write size"):
        docker_client_for_files.write_file("cid-1", "x" * 100, "/work/file.txt")

    container.put_archive.assert_not_called()


def test_write_file_raises_file_not_found_when_container_missing(
    docker_client_for_files: DockerClient,
) -> None:
    docker_client_for_files._client.containers.get.side_effect = docker.errors.NotFound("gone")

    with pytest.raises(FileNotFoundError, match="Container not found"):
        docker_client_for_files.write_file("no-such", "content", "/work/f.txt")


def test_write_file_raises_when_container_not_running(
    docker_client_for_files: DockerClient,
) -> None:
    container = MagicMock()
    container.status = "exited"
    docker_client_for_files._client.containers.get.return_value = container

    with pytest.raises(RuntimeError, match="not running"):
        docker_client_for_files.write_file("cid-1", "data", "/work/f.txt")


def test_write_file_sets_executable_permissions(docker_client_for_files: DockerClient) -> None:
    container = _running_container(docker_client_for_files)

    docker_client_for_files.write_file("cid-1", "#!/bin/sh\necho hi", "/work/run.sh")

    _, tar_data = container.put_archive.call_args[0]
    with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
        entry = tar.getmembers()[0]
        assert entry.mode & 0o111, "File should have executable bits set"


def test_write_file_empty_content_creates_empty_file(
    docker_client_for_files: DockerClient,
) -> None:
    container = _running_container(docker_client_for_files)

    result = docker_client_for_files.write_file("cid-1", "", "/work/empty.txt")

    assert "empty.txt" in result
    _, tar_data = container.put_archive.call_args[0]
    with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
        entry = tar.getmembers()[0]
        assert entry.size == 0


def test_docker_config_file_size_limit_defaults() -> None:
    """DockerConfig ships with 10 MB read limit and 5 MB write limit by default."""
    config = DockerConfig(data_dir="/tmp/test-defaults")
    assert config.max_read_file_size == 10 * 1024 * 1024
    assert config.max_write_file_size == 5 * 1024 * 1024


def test_normalize_path_variations() -> None:
    """_normalize_path prepends /work/ for relative paths and leaves absolute paths unchanged."""
    assert DockerClient._normalize_path("scan.py") == "/work/scan.py"
    assert DockerClient._normalize_path("dir/findings.json") == "/work/dir/findings.json"
    assert DockerClient._normalize_path("/work/already.txt") == "/work/already.txt"
    assert DockerClient._normalize_path("/etc/passwd") == "/etc/passwd"
    assert DockerClient._normalize_path("/tmp/nmap_output.txt") == "/tmp/nmap_output.txt"


def test_is_container_running_true_when_running_without_health(
    docker_client_for_files: DockerClient,
) -> None:
    container = MagicMock()
    container.attrs = {"State": {"Status": "running"}}
    docker_client_for_files._client.containers.get.return_value = container

    assert docker_client_for_files.is_container_running("cid-1") is True
    container.reload.assert_called_once()


def test_is_container_running_false_when_unhealthy(docker_client_for_files: DockerClient) -> None:
    container = MagicMock()
    container.attrs = {"State": {"Status": "running", "Health": {"Status": "unhealthy"}}}
    docker_client_for_files._client.containers.get.return_value = container

    assert docker_client_for_files.is_container_running("cid-1") is False


def test_is_container_running_false_when_not_found(docker_client_for_files: DockerClient) -> None:
    docker_client_for_files._client.containers.get.side_effect = docker.errors.NotFound("missing")

    assert docker_client_for_files.is_container_running("missing") is False


def test_exec_command_returns_output_for_success(docker_client_for_files: DockerClient) -> None:
    stream = MagicMock()
    raw_stream = MagicMock()
    raw_stream.recv.side_effect = [b"hello\n", b""]
    stream._sock = raw_stream

    docker_client_for_files.is_container_running = MagicMock(return_value=True)
    docker_client_for_files._client.api.exec_create.return_value = {"Id": "exec-1"}
    docker_client_for_files._client.api.exec_start.return_value = stream
    docker_client_for_files._client.api.exec_inspect.return_value = {
        "Running": False,
        "ExitCode": 0,
    }

    result = docker_client_for_files.exec_command("cid-1", "echo hello", "/work", 10, False)

    assert result == "hello\n"


def test_exec_command_returns_success_message_on_empty_output(
    docker_client_for_files: DockerClient,
) -> None:
    stream = MagicMock()
    raw_stream = MagicMock()
    raw_stream.recv.side_effect = [b""]
    stream._sock = raw_stream

    docker_client_for_files.is_container_running = MagicMock(return_value=True)
    docker_client_for_files._client.api.exec_create.return_value = {"Id": "exec-2"}
    docker_client_for_files._client.api.exec_start.return_value = stream
    docker_client_for_files._client.api.exec_inspect.return_value = {
        "Running": False,
        "ExitCode": 0,
    }

    result = docker_client_for_files.exec_command("cid-1", "true", "/work", 10, False)

    assert result == "Command completed successfully with exit code 0"


def test_exec_command_timeout_returns_partial_and_hint(
    docker_client_for_files: DockerClient,
) -> None:
    stream = MagicMock()
    raw_stream = MagicMock()
    raw_stream.recv.side_effect = [b"partial output"]
    raw_stream.settimeout = MagicMock()
    stream._sock = raw_stream

    docker_client_for_files.is_container_running = MagicMock(return_value=True)
    docker_client_for_files._client.api.exec_create.return_value = {"Id": "exec-3"}
    docker_client_for_files._client.api.exec_start.return_value = stream
    docker_client_for_files._client.api.exec_inspect.return_value = {
        "Running": True,
        "ExitCode": None,
    }

    with patch("pentest.docker.client.time.monotonic", side_effect=[0.0, 0.1, 3.0]):
        result = docker_client_for_files.exec_command("cid-1", "sleep 10", "/work", 2, False)

    assert "partial output" in result
    assert "Command timed out after 2s" in result


def test_exec_command_detach_returns_background_message(
    docker_client_for_files: DockerClient,
) -> None:
    stream = MagicMock()
    raw_stream = MagicMock()
    raw_stream.recv.side_effect = [b"x"]
    raw_stream.settimeout = MagicMock()
    stream._sock = raw_stream

    docker_client_for_files.is_container_running = MagicMock(return_value=True)
    docker_client_for_files._client.api.exec_create.return_value = {"Id": "exec-4"}
    docker_client_for_files._client.api.exec_start.return_value = stream
    docker_client_for_files._client.api.exec_inspect.return_value = {
        "Running": True,
        "ExitCode": None,
    }

    with patch("pentest.docker.client.time.monotonic", side_effect=[0.0, 1.0]):
        result = docker_client_for_files.exec_command("cid-1", "sleep 60", "/work", 10, True)

    assert result == "Command started in background"


def test_exec_command_clamps_timeout_to_max_1200(docker_client_for_files: DockerClient) -> None:
    stream = MagicMock()
    raw_stream = MagicMock()
    raw_stream.recv.side_effect = [b"out"]
    raw_stream.settimeout = MagicMock()
    stream._sock = raw_stream

    docker_client_for_files.is_container_running = MagicMock(return_value=True)
    docker_client_for_files._client.api.exec_create.return_value = {"Id": "exec-5"}
    docker_client_for_files._client.api.exec_start.return_value = stream
    docker_client_for_files._client.api.exec_inspect.return_value = {
        "Running": True,
        "ExitCode": None,
    }

    with patch("pentest.docker.client.time.monotonic", side_effect=[0.0, 2000.0]):
        result = docker_client_for_files.exec_command("cid-1", "sleep 9999", "/work", 9999, False)

    assert "Command timed out after 1200s" in result
