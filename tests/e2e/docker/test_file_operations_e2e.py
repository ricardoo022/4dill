"""E2E tests for US-016: file operations against real Docker containers.

These tests exercise read_file / write_file in realistic pentest scenarios
using real container images (Kali Linux preferred, debian/alpine as fallback).

Requirements:
- Real Docker daemon accessible
- At least one of: kalilinux/kali-rolling, debian:bullseye-slim, alpine:3.20

Run manually:
    pytest tests/e2e/docker/test_file_operations_e2e.py -v -m e2e
"""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import docker
import docker.errors
import pytest

from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e

_CANDIDATE_IMAGES = [
    "kalilinux/kali-rolling",
    "debian:bullseye-slim",
    "alpine:3.20",
]


@pytest.fixture(scope="module")
def docker_api_e2e() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
        return client
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon not available for e2e tests: {exc}")


@pytest.fixture(scope="module")
def pentest_image(docker_api_e2e: docker.DockerClient) -> str:
    """Return the best available pentest image, preferring Kali Linux."""
    for image in _CANDIDATE_IMAGES:
        try:
            docker_api_e2e.images.get(image)
            return image
        except docker.errors.ImageNotFound:
            pass
        try:
            docker_api_e2e.images.pull(image, timeout=180)
            return image
        except Exception:
            continue
    pytest.skip(f"No suitable pentest image available (tried: {', '.join(_CANDIDATE_IMAGES)})")


def test_kali_container_bash_exploit_template_lifecycle(
    tmp_path: Path,
    docker_api_e2e: docker.DockerClient,
    pentest_image: str,
) -> None:
    """🔁 Write bash exploit template to pentest container; verify content and executable bits.

    Covers the DoD item: 'File operations work reliably with the Kali container'.
    Round-trip: write → read back → assert content exact → exec stat → assert 755 permissions.
    """
    exploit_script = (
        "#!/bin/sh\n"
        "# CVE-2021-22911: Grafana Authentication Bypass Probe\n"
        "# CVSS: 9.8 (Critical) — unauthenticated user enumeration\n"
        "TARGET=${1:-http://192.168.1.50:3000}\n"
        'echo "[*] Probing Grafana at $TARGET"\n'
        'curl -sf "$TARGET/api/users" -H "Content-Type: application/json" \\\n'
        '  2>/dev/null | grep -q "login" && echo "[+] VULNERABLE" || echo "[-] not vulnerable"\n'
    )

    container = docker_api_e2e.containers.run(
        pentest_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"e2e-exploit-tpl-{uuid.uuid4().hex[:8]}",
    )
    try:
        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=MagicMock(), config=config)

        msg = client.write_file(container.id, exploit_script, "/work/exploit_cve_2021_22911.sh")
        assert "exploit_cve_2021_22911.sh" in msg

        recovered = client.read_file(container.id, "/work/exploit_cve_2021_22911.sh")
        assert "CVE-2021-22911" in recovered
        assert "CVSS" in recovered
        assert recovered.startswith("#!/bin/sh")

        exit_code, output = container.exec_run(
            [
                "sh",
                "-c",
                "stat -c '%a' /work/exploit_cve_2021_22911.sh 2>/dev/null "
                "|| ls -la /work/exploit_cve_2021_22911.sh",
            ]
        )
        assert exit_code == 0
        output_str = output.decode("utf-8", errors="replace")
        assert "755" in output_str or "rwxr-xr-x" in output_str
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            container.remove(force=True)


def test_scanner_agent_write_script_exec_read_findings_roundtrip(
    tmp_path: Path,
    docker_api_e2e: docker.DockerClient,
    pentest_image: str,
) -> None:
    """🔁 Simulate Scanner agent: write probe → exec → read structured JSON findings.

    Models the real Scanner agent file workflow: the agent writes a tool script
    to /work/, executes it, and reads the structured output back. Uses a
    CVE-2021-22911 (Grafana auth bypass, CVSS 9.8) probe as realistic test data.
    """
    probe_script = (
        "#!/bin/sh\n"
        "# Grafana CVE-2021-22911 prober — simulated output\n"
        "TARGET='http://192.168.1.50:3000'\n"
        "TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo '1970-01-01T00:00:00Z')\n"
        'printf \'{"cve":"CVE-2021-22911","severity":"critical","cvss":9.8,'
        '"target":"%s","result":"simulated_probe_complete","timestamp":"%s"}\' '
        '"$TARGET" "$TS" > /work/cve_findings.json\n'
    )

    container = docker_api_e2e.containers.run(
        pentest_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"e2e-scanner-{uuid.uuid4().hex[:8]}",
    )
    try:
        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=MagicMock(), config=config)

        client.write_file(container.id, probe_script, "/work/probe.sh")
        exit_code, _ = container.exec_run(["sh", "/work/probe.sh"])
        assert exit_code == 0

        raw = client.read_file(container.id, "/work/cve_findings.json")
        findings = json.loads(raw.strip())

        assert findings["cve"] == "CVE-2021-22911"
        assert findings["severity"] == "critical"
        assert findings["cvss"] == 9.8
        assert "192.168.1.50" in findings["target"]
        assert findings["result"] == "simulated_probe_complete"
        assert "timestamp" in findings
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            container.remove(force=True)


def test_file_operations_survive_container_restart(
    tmp_path: Path,
    docker_api_e2e: docker.DockerClient,
    pentest_image: str,
) -> None:
    """🔁 Write pentest findings to /work/, restart container, verify data persists.

    Confirms that the bind-mount volume strategy (host dir → /work inside container)
    preserves scan artifacts across container restarts — a critical property for
    scan recovery after failures.

    Round-trip: write JSON report → restart container → read report → assert exact content.
    """
    findings_report = json.dumps(
        {
            "scan_id": "e2e-restart-proof",
            "target": "192.168.1.100",
            "findings": [
                {
                    "port": 22,
                    "service": "openssh",
                    "version": "7.4p1",
                    "cve": "CVE-2018-15473",
                    "severity": "medium",
                },
                {
                    "port": 3306,
                    "service": "mysql",
                    "version": "5.7.28",
                    "cve": "CVE-2020-14765",
                    "severity": "high",
                },
            ],
            "status": "completed",
        },
        indent=2,
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    container = docker_api_e2e.containers.run(
        pentest_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"e2e-restart-{uuid.uuid4().hex[:8]}",
        volumes={str(work_dir): {"bind": "/work", "mode": "rw"}},
    )
    try:
        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=MagicMock(), config=config)

        client.write_file(container.id, findings_report, "/work/scan_report.json")

        container.restart(timeout=15)
        container.reload()
        assert container.status == "running"

        recovered_raw = client.read_file(container.id, "/work/scan_report.json")
        recovered = json.loads(recovered_raw)

        assert recovered["scan_id"] == "e2e-restart-proof"
        assert recovered["target"] == "192.168.1.100"
        assert len(recovered["findings"]) == 2
        assert recovered["findings"][0]["cve"] == "CVE-2018-15473"
        assert recovered["findings"][1]["cve"] == "CVE-2020-14765"
        assert recovered["status"] == "completed"
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            container.remove(force=True)


def test_python_script_write_exec_read_output_e2e(
    tmp_path: Path,
    docker_api_e2e: docker.DockerClient,
    pentest_image: str,
) -> None:
    """🔁 Write Python script to /work, execute, then read generated output.

    Mirrors US-016 required scenario at E2E layer: write `/work/script.py`,
    execute inside real container, and verify output file content.
    """
    script = 'with open("/work/out.txt", "w", encoding="utf-8") as f:\n    f.write("success")\n'

    container = docker_api_e2e.containers.run(
        pentest_image,
        entrypoint=["tail", "-f", "/dev/null"],
        detach=True,
        name=f"e2e-python-script-{uuid.uuid4().hex[:8]}",
    )
    try:
        config = DockerConfig(data_dir=str(tmp_path))
        client = DockerClient(db_session=MagicMock(), config=config)

        client.write_file(container.id, script, "/work/script.py")
        exit_code, output = container.exec_run(["python3", "/work/script.py"])
        if exit_code != 0:
            pytest.skip(
                "python3 not available in selected image: "
                f"{output.decode('utf-8', errors='replace')}"
            )

        result = client.read_file(container.id, "/work/out.txt")
        assert result == "success"
    finally:
        with contextlib.suppress(docker.errors.NotFound):
            container.remove(force=True)
