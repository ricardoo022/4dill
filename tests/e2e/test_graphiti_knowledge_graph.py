"""End-to-end tests for the live Graphiti knowledge graph integration."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio

from pentest.graphiti import (
    GraphitiClient,
    GraphitiError,
    GraphitiMessage,
    GraphitiOperationResult,
    GraphitiSearchResponse,
)
from pentest.tools.graphiti_search import create_graphiti_search_tool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

pytestmark = pytest.mark.e2e

GRAPHITI_E2E_URL = (
    os.getenv("GRAPHITI_E2E_URL") or os.getenv("GRAPHITI_URL") or "http://localhost:8000"
)
GRAPHITI_E2E_TIMEOUT = float(os.getenv("GRAPHITI_E2E_TIMEOUT", "60"))
GRAPHITI_E2E_POLL_ATTEMPTS = int(os.getenv("GRAPHITI_E2E_POLL_ATTEMPTS", "6"))
GRAPHITI_E2E_POLL_INTERVAL = float(os.getenv("GRAPHITI_E2E_POLL_INTERVAL", "5"))
GRAPHITI_FORCE_VALIDATE = os.getenv("GRAPHITI_FORCE_VALIDATE", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _candidate_graphiti_targets() -> list[tuple[str, str | None]]:
    explicit_urls = [
        os.getenv("GRAPHITI_E2E_URL"),
        os.getenv("GRAPHITI_URL"),
    ]
    candidates: list[tuple[str, str | None]] = [
        (url.rstrip("/"), None) for url in explicit_urls if url
    ]
    candidates.extend(
        [
            ("http://localhost:8000", None),
            ("http://127.0.0.1:8000", None),
        ]
    )
    docker_path = shutil.which("docker") or next(
        (path for path in ("/usr/bin/docker", "/bin/docker") if os.path.exists(path)),
        None,
    )
    if not docker_path:
        return candidates

    try:
        ps_result = subprocess.run(
            [docker_path, "ps", "--format", "{{.Names}}\t{{.Image}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return candidates

    for line in ps_result.stdout.splitlines():
        try:
            name, image = line.split("\t", maxsplit=1)
        except ValueError:
            continue
        if "graphiti" not in name.lower() and "graphiti" not in image.lower():
            continue

        try:
            inspect_result = subprocess.run(
                [
                    docker_path,
                    "inspect",
                    "-f",
                    "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                    name,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except OSError:
            continue

        ip_address = inspect_result.stdout.strip()
        if ip_address:
            candidates.append((f"http://{ip_address}:8000", name))

    return list(dict.fromkeys(candidates))


def _graphiti_container_enabled(container_name: str) -> bool | None:
    docker_path = shutil.which("docker") or next(
        (path for path in ("/usr/bin/docker", "/bin/docker") if os.path.exists(path)),
        None,
    )
    if not docker_path:
        return None

    try:
        result = subprocess.run(
            [
                docker_path,
                "inspect",
                "-f",
                "{{range .Config.Env}}{{println .}}{{end}}",
                container_name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("GRAPHITI_ENABLED="):
            value = line.partition("=")[2].strip().lower()
            return value in {"1", "true", "yes", "on"}

    return None


def _build_seed_messages(run_id: str) -> list[GraphitiMessage]:
    atlas_host = f"atlas-{run_id}.internal"
    boreal_host = f"boreal-{run_id}.internal"
    return [
        GraphitiMessage(
            role="agent",
            content=(
                f"E2E run {run_id}: Host {atlas_host} exposes TCP ports 22 and 443, "
                "runs nginx 1.26.1, and the analyst confirmed with nmap that SSH and "
                f"HTTPS were reachable. The same run confirmed with nuclei that {atlas_host} "
                "is affected by CVE-2099-4242."
            ),
        ),
        GraphitiMessage(
            role="agent",
            content=(
                f"E2E run {run_id}: Host {boreal_host} exposes TCP port 8443 and runs "
                "Grafana, while the broader environment also includes a Postgres-backed "
                "analytics cluster and shared reconnaissance context."
            ),
        ),
    ]


def _result_text(result: GraphitiSearchResponse) -> str:
    parts: list[str] = []
    for edge in result.edges:
        if edge.fact:
            parts.append(edge.fact)
        if edge.name:
            parts.append(edge.name)
    for node in result.nodes:
        if node.name:
            parts.append(node.name)
        if node.summary:
            parts.append(node.summary)
        parts.extend(node.labels)
    return " ".join(parts).lower()


async def _wait_for_seed_indexing(
    client: GraphitiClient, dataset: dict[str, object]
) -> GraphitiSearchResponse:
    atlas_host = str(dataset["atlas_host"])
    group_id = str(dataset["group_id"])

    last_result = GraphitiSearchResponse()
    await asyncio.sleep(GRAPHITI_E2E_POLL_INTERVAL)
    for _ in range(GRAPHITI_E2E_POLL_ATTEMPTS):
        try:
            last_result = await client.recent_context_search(
                atlas_host,
                group_ids=[group_id],
                timeout=GRAPHITI_E2E_TIMEOUT,
            )
        except GraphitiError as exc:
            message = f"Graphiti e2e search failed during indexing wait: {exc}"
            if GRAPHITI_FORCE_VALIDATE:
                pytest.fail(message)
            pytest.skip(message)

        if last_result.edges or last_result.nodes:
            return last_result
        await asyncio.sleep(GRAPHITI_E2E_POLL_INTERVAL)

    message = (
        "Graphiti accepted the seed dataset but did not materialize it in Neo4j within the "
        "polling window. This means the HTTP request succeeded, but US-036 graph indexing "
        "remains unverified. Check Graphiti worker readiness, API credentials, and Neo4j "
        "connectivity. Set GRAPHITI_FORCE_VALIDATE=false to downgrade this to a skip."
    )
    if GRAPHITI_FORCE_VALIDATE:
        pytest.fail(message)
    pytest.skip(message)


def _assert_non_empty_result(result: GraphitiSearchResponse) -> None:
    assert result.edges or result.nodes, "Expected at least one fact or entity in the response"


def _assert_readable_tool_result(result: str, query: str) -> None:
    assert result.startswith("Knowledge graph results for ")
    assert query in result
    assert "{'facts'" not in result
    assert "graphiti_search tool error" not in result


@pytest_asyncio.fixture
async def graphiti_client() -> AsyncGenerator[GraphitiClient, None]:
    last_error: Exception | None = None
    client: GraphitiClient | None = None

    for url, container_name in _candidate_graphiti_targets():
        if container_name:
            enabled = _graphiti_container_enabled(container_name)
            if enabled is False:
                pytest.skip(
                    f"Graphiti container {container_name} is running with GRAPHITI_ENABLED=false; "
                    "e2e ingestion is disabled."
                )

        try:
            client = await GraphitiClient.create(
                url=url,
                enabled=True,
                timeout=GRAPHITI_E2E_TIMEOUT,
            )
            break
        except Exception as exc:
            last_error = exc

    if client is None:
        pytest.skip(
            f"Graphiti e2e service is not reachable at any candidate URL; last error: {last_error}"
        )

    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def ingested_graphiti_dataset(
    graphiti_client: GraphitiClient,
) -> dict[str, object]:
    run_id = uuid4().hex[:10]
    group_id = f"kg-e2e-{run_id}"
    messages = _build_seed_messages(run_id)
    atlas_host = f"atlas-{run_id}.internal"

    operation = await graphiti_client.add_messages(
        messages,
        group_id=group_id,
        timeout=GRAPHITI_E2E_TIMEOUT,
    )
    dataset: dict[str, object] = {
        "run_id": run_id,
        "group_id": group_id,
        "atlas_host": atlas_host,
        "boreal_host": f"boreal-{run_id}.internal",
        "data_host": f"data-{run_id}.internal",
        "operation": operation,
    }
    graphiti_client.default_group_id = group_id
    return dataset


@pytest_asyncio.fixture
async def seeded_graphiti_dataset(
    graphiti_client: GraphitiClient,
    ingested_graphiti_dataset: dict[str, object],
) -> dict[str, object]:
    dataset = dict(ingested_graphiti_dataset)
    dataset["warmup_result"] = await _wait_for_seed_indexing(graphiti_client, dataset)
    return dataset


@pytest.fixture
def graphiti_search_tool(graphiti_client: GraphitiClient):
    return create_graphiti_search_tool(graphiti_client)


async def test_graphiti_e2e_service_healthcheck(graphiti_client: GraphitiClient) -> None:
    await graphiti_client.ensure_healthy()
    assert graphiti_client._health_checked is True


async def test_graphiti_e2e_seed_ingestion_reports_success(
    ingested_graphiti_dataset: dict[str, object],
) -> None:
    operation = ingested_graphiti_dataset["operation"]
    assert isinstance(operation, GraphitiOperationResult)
    assert operation.success is True, "This only validates request acceptance, not graph indexing"


async def test_graphiti_e2e_recent_context_search_returns_seeded_host(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.recent_context_search(
        atlas_host,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)
    assert atlas_host.lower() in _result_text(result)


async def test_graphiti_e2e_recent_context_search_respects_group_isolation(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    wrong_group = f"missing-{seeded_graphiti_dataset['group_id']}"
    result = await graphiti_client.recent_context_search(
        atlas_host,
        group_ids=[wrong_group],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    assert not result.edges
    assert not result.nodes


async def test_graphiti_e2e_temporal_search_returns_recent_findings(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.temporal_search(
        atlas_host,
        recency_window="7d",
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)


async def test_graphiti_e2e_successful_tools_search_finds_nmap_context(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.successful_tools_search(
        f"nmap {atlas_host}",
        min_mentions=1,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)
    assert "nmap" in _result_text(result)


async def test_graphiti_e2e_successful_tools_search_finds_nuclei_context(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.successful_tools_search(
        f"nuclei {atlas_host}",
        min_mentions=1,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)
    assert "nuclei" in _result_text(result) or "cve" in _result_text(result)


async def test_graphiti_e2e_episode_context_search_returns_seeded_context(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.episode_context_search(
        atlas_host,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)


async def test_graphiti_e2e_diverse_search_returns_non_empty_response(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    query = f"{seeded_graphiti_dataset['atlas_host']} {seeded_graphiti_dataset['boreal_host']}"
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.diverse_search(
        query,
        diversity_level=2,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    _assert_non_empty_result(result)


async def test_graphiti_e2e_entity_by_label_search_returns_response(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.entity_by_label_search(
        atlas_host,
        node_labels=["Host", "Service", "Entity"],
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    assert isinstance(result, GraphitiSearchResponse)
    assert isinstance(result.nodes, list)
    assert isinstance(result.edges, list)


async def test_graphiti_e2e_entity_relationship_search_returns_response(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.entity_relationship_search(
        atlas_host,
        center_node_uuid="00000000-0000-0000-0000-000000000123",
        max_depth=2,
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    assert isinstance(result, GraphitiSearchResponse)
    assert isinstance(result.nodes, list)
    assert isinstance(result.edges, list)


async def test_graphiti_e2e_nonexistent_query_returns_empty_response(
    graphiti_client: GraphitiClient,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    group_id = str(seeded_graphiti_dataset["group_id"])
    result = await graphiti_client.recent_context_search(
        f"nonexistent-{uuid4().hex}",
        group_ids=[group_id],
        timeout=GRAPHITI_E2E_TIMEOUT,
    )

    assert not result.edges
    assert not result.nodes


async def test_graphiti_e2e_tool_recent_context_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    result = await graphiti_search_tool.arun(
        {
            "search_type": "recent_context",
            "query": atlas_host,
            "message": "Search recent graph context",
        }
    )

    _assert_readable_tool_result(result, atlas_host)


async def test_graphiti_e2e_tool_successful_tools_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    query = f"nmap {seeded_graphiti_dataset['atlas_host']}"
    result = await graphiti_search_tool.arun(
        {
            "search_type": "successful_tools",
            "query": query,
            "min_mentions": 1,
            "message": "Search successful tools",
        }
    )

    _assert_readable_tool_result(result, query)


async def test_graphiti_e2e_tool_episode_context_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    result = await graphiti_search_tool.arun(
        {
            "search_type": "episode_context",
            "query": atlas_host,
            "message": "Search episode context",
        }
    )

    _assert_readable_tool_result(result, atlas_host)


async def test_graphiti_e2e_tool_diverse_results_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    query = f"{seeded_graphiti_dataset['atlas_host']} {seeded_graphiti_dataset['boreal_host']}"
    result = await graphiti_search_tool.arun(
        {
            "search_type": "diverse_results",
            "query": query,
            "diversity_level": 2,
            "message": "Search diverse graph context",
        }
    )

    _assert_readable_tool_result(result, query)


async def test_graphiti_e2e_tool_entity_by_label_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    result = await graphiti_search_tool.arun(
        {
            "search_type": "entity_by_label",
            "query": atlas_host,
            "node_labels": ["Host", "Service", "Entity"],
            "message": "Search entities by label",
        }
    )

    _assert_readable_tool_result(result, atlas_host)


async def test_graphiti_e2e_tool_entity_relationships_formats_text(
    graphiti_search_tool,
    seeded_graphiti_dataset: dict[str, object],
) -> None:
    atlas_host = str(seeded_graphiti_dataset["atlas_host"])
    result = await graphiti_search_tool.arun(
        {
            "search_type": "entity_relationships",
            "query": atlas_host,
            "center_node_uuid": "00000000-0000-0000-0000-000000000123",
            "max_depth": 2,
            "message": "Search entity relationships",
        }
    )

    _assert_readable_tool_result(result, atlas_host)


async def test_graphiti_e2e_tool_invalid_search_type_returns_clear_error(
    graphiti_search_tool,
) -> None:
    result = await graphiti_search_tool.arun(
        {
            "search_type": "totally_invalid",
            "query": "atlas",
            "message": "Invalid search type",
        }
    )

    assert "invalid search_type" in result


async def test_graphiti_e2e_tool_disabled_mode_returns_clear_message() -> None:
    disabled_client = GraphitiClient(url=GRAPHITI_E2E_URL, enabled=False)
    tool = create_graphiti_search_tool(disabled_client)

    result = await tool.arun(
        {
            "search_type": "recent_context",
            "query": "atlas",
            "message": "Disabled graph search",
        }
    )

    assert result == "Knowledge graph not enabled"
    await disabled_client.aclose()
