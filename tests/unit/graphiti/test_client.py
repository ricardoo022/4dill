"""US-035: Graphiti client tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from pentest.graphiti import (
    GraphitiClient,
    GraphitiConnectionError,
    GraphitiMessage,
    GraphitiNotEnabledError,
    GraphitiTimeoutError,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.asyncio
async def test_disabled_client_add_messages_is_noop():
    client = GraphitiClient(url="http://graphiti", enabled=False)

    result = await client.add_messages([{"role": "agent", "content": "nmap found port 443"}])

    assert result.success is True
    assert "disabled" in result.message.lower()
    await client.aclose()


@pytest.mark.asyncio
async def test_disabled_client_search_raises_not_enabled():
    client = GraphitiClient(url="http://graphiti", enabled=False)

    with pytest.raises(GraphitiNotEnabledError, match="not enabled"):
        await client.temporal_search("nginx vulnerabilities")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_enabled_client_healthcheck_passes_on_create():
    async with httpx.AsyncClient(base_url="http://graphiti") as http_client:
        respx.get("http://graphiti/healthcheck").respond(200, json={"status": "healthy"})

        client = await GraphitiClient.create(
            url="http://graphiti",
            enabled=True,
            http_client=http_client,
        )

        assert client.enabled is True
        assert client.url == "http://graphiti"


@pytest.mark.asyncio
@respx.mock
async def test_enabled_client_invalid_url_fails_with_clear_error():
    async with httpx.AsyncClient(base_url="http://invalid:9999") as http_client:
        respx.get("http://invalid:9999/healthcheck").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        respx.get("http://invalid:9999/health").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(GraphitiConnectionError, match="Failed to connect to Graphiti"):
            await GraphitiClient.create(
                url="http://invalid:9999",
                enabled=True,
                http_client=http_client,
            )


@pytest.mark.asyncio
@respx.mock
async def test_add_messages_queues_messages():
    async with httpx.AsyncClient(base_url="http://graphiti") as http_client:
        respx.get("http://graphiti/healthcheck").respond(200, json={"status": "healthy"})
        route = respx.post("http://graphiti/messages").respond(
            202, json={"message": "Messages added to processing queue", "success": True}
        )

        client = await GraphitiClient.create(
            url="http://graphiti",
            enabled=True,
            http_client=http_client,
        )
        result = await client.add_messages(
            [GraphitiMessage(role="agent", content="nmap found port 443 running nginx 1.24")]
        )

        assert result.success is True
        sent_json = json.loads(route.calls[0].request.content.decode())
        assert sent_json["group_id"] == "default"
        assert sent_json["messages"][0]["content"] == "nmap found port 443 running nginx 1.24"
        assert sent_json["messages"][0]["author"] == "agent"
        assert sent_json["messages"][0]["role_type"] == "assistant"


SEARCH_CASES: list[tuple[str, dict[str, object]]] = [
    ("temporal_search", {"query": "nginx vulnerabilities", "recency_window": "7d"}),
    (
        "entity_relationship_search",
        {"query": "nginx vulnerabilities", "center_node_uuid": "node-123", "max_depth": 2},
    ),
    ("diverse_search", {"query": "nginx vulnerabilities", "diversity_level": 2}),
    ("episode_context_search", {"query": "nginx vulnerabilities"}),
    ("successful_tools_search", {"query": "nginx vulnerabilities", "min_mentions": 3}),
    ("recent_context_search", {"query": "nginx vulnerabilities", "recency_window": "24h"}),
    (
        "entity_by_label_search",
        {"query": "nginx vulnerabilities", "node_labels": ["Service", "CVE"]},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method_name", "kwargs"), SEARCH_CASES)
@respx.mock
async def test_search_methods_return_typed_results(method_name: str, kwargs: dict[str, object]):
    async with httpx.AsyncClient(base_url="http://graphiti") as http_client:
        respx.get("http://graphiti/healthcheck").respond(200, json={"status": "healthy"})
        route = respx.post("http://graphiti/search").respond(
            200,
            json={
                "facts": [
                    {
                        "uuid": "edge-1",
                        "name": "runs_on",
                        "fact": "Port 443 runs nginx 1.24",
                        "created_at": "2026-04-06T10:00:00Z",
                    }
                ]
            },
        )

        client = await GraphitiClient.create(
            url="http://graphiti",
            enabled=True,
            http_client=http_client,
        )
        method: Callable[..., object] = getattr(client, method_name)
        result = await method(**kwargs)

        assert result.edges[0].uuid == "edge-1"
        assert result.facts[0].fact == "Port 443 runs nginx 1.24"
        sent_json = json.loads(route.calls[0].request.content.decode())
        assert sent_json["group_ids"] == ["default"]
        assert "nginx vulnerabilities" in sent_json["query"]


@pytest.mark.asyncio
@respx.mock
async def test_search_timeout_raises_clear_error():
    async with httpx.AsyncClient(base_url="http://graphiti") as http_client:
        respx.get("http://graphiti/healthcheck").respond(200, json={"status": "healthy"})
        respx.post("http://graphiti/search").mock(side_effect=httpx.ReadTimeout("slow"))

        client = await GraphitiClient.create(
            url="http://graphiti",
            enabled=True,
            http_client=http_client,
        )

        with pytest.raises(GraphitiTimeoutError, match="Timed out"):
            await client.temporal_search("nginx vulnerabilities", timeout=0.01)
