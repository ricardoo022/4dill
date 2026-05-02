"""US-036: Graphiti search tool handler tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pentest.graphiti import GraphitiEdgeResult, GraphitiNodeResult, GraphitiSearchResponse
from pentest.models.tool_args import GRAPHITI_SEARCH_TYPES, GraphitiSearchAction
from pentest.tools.graphiti_search import create_graphiti_search_tool
from pentest.tools.registry import (
    GRAPHITI_SEARCH_TOOL_DEFINITION,
    TOOL_REGISTRY,
    SearchVectorDbToolType,
)


def _sample_result() -> GraphitiSearchResponse:
    return GraphitiSearchResponse(
        edges=[GraphitiEdgeResult(uuid="edge-1", fact="Port 443 runs nginx 1.24", name="runs_on")]
    )


def _sample_node_result() -> GraphitiSearchResponse:
    return GraphitiSearchResponse(
        nodes=[
            GraphitiNodeResult(
                uuid="node-1",
                name="nginx",
                labels=["service"],
                summary="Reverse proxy service",
            )
        ]
    )


def test_graphiti_search_action_schema_validation():
    action = GraphitiSearchAction(
        search_type="recent_context",
        query="nmap results",
        message="search graph",
    )

    assert action.search_type == "recent_context"
    schema = GraphitiSearchAction.model_json_schema()
    assert schema["properties"]["search_type"]["enum"] == GRAPHITI_SEARCH_TYPES


def test_graphiti_search_tool_registered_with_json_schema():
    assert "graphiti_search" in TOOL_REGISTRY
    assert GRAPHITI_SEARCH_TOOL_DEFINITION.name == "graphiti_search"
    assert GRAPHITI_SEARCH_TOOL_DEFINITION.tool_type == SearchVectorDbToolType
    assert "search_type" in GRAPHITI_SEARCH_TOOL_DEFINITION.json_schema["properties"]


@pytest.mark.asyncio
async def test_recent_context_maps_to_client_method():
    client = MagicMock()
    client.enabled = True
    client.recent_context_search = AsyncMock(return_value=_sample_result())

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "recent_context",
            "query": "nmap results",
            "message": "search graph",
        }
    )

    client.recent_context_search.assert_awaited_once_with("nmap results", recency_window=None)
    assert "Knowledge graph results" in result
    assert "Port 443 runs nginx 1.24" in result


@pytest.mark.asyncio
async def test_entity_relationships_maps_to_client_method():
    client = MagicMock()
    client.enabled = True
    client.entity_relationship_search = AsyncMock(return_value=_sample_result())

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "entity_relationships",
            "query": "nginx relationships",
            "center_node_uuid": "node-123",
            "max_depth": 2,
            "message": "search graph",
        }
    )

    client.entity_relationship_search.assert_awaited_once_with(
        "nginx relationships",
        center_node_uuid="node-123",
        max_depth=2,
    )
    assert "Knowledge graph results" in result


@pytest.mark.asyncio
async def test_entity_relationships_requires_center_node_uuid():
    client = MagicMock()
    client.enabled = True
    client.entity_relationship_search = AsyncMock()

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "entity_relationships",
            "query": "nginx relationships",
            "message": "search graph",
        }
    )

    client.entity_relationship_search.assert_not_awaited()
    assert (
        result
        == "graphiti_search tool error: center_node_uuid is required for entity_relationships"
    )


@pytest.mark.asyncio
async def test_disabled_graphiti_returns_readable_message():
    client = MagicMock()
    client.enabled = False

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "recent_context",
            "query": "nmap results",
            "message": "search graph",
        }
    )

    assert result == "Knowledge graph not enabled"


@pytest.mark.asyncio
async def test_invalid_search_type_returns_clear_error():
    client = MagicMock()
    client.enabled = True

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "invalid",
            "query": "nmap results",
            "message": "search graph",
        }
    )

    assert "invalid search_type" in result


@pytest.mark.asyncio
async def test_result_is_formatted_text_not_raw_json():
    client = MagicMock()
    client.enabled = True
    client.episode_context_search = AsyncMock(return_value=_sample_result())

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "episode_context",
            "query": "agent reasoning",
            "message": "search graph",
        }
    )

    assert "Facts:" in result
    assert "Port 443 runs nginx 1.24" in result
    assert "{'facts'" not in result


@pytest.mark.asyncio
async def test_entity_by_label_requires_node_labels():
    client = MagicMock()
    client.enabled = True
    client.entity_by_label_search = AsyncMock()

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "entity_by_label",
            "query": "nginx",
            "message": "search graph",
        }
    )

    client.entity_by_label_search.assert_not_awaited()
    assert result == "graphiti_search tool error: node_labels is required for entity_by_label"


@pytest.mark.asyncio
async def test_entity_by_label_maps_to_client_method():
    client = MagicMock()
    client.enabled = True
    client.entity_by_label_search = AsyncMock(return_value=_sample_node_result())

    tool = create_graphiti_search_tool(client)
    result = await tool.arun(
        {
            "search_type": "entity_by_label",
            "query": "nginx",
            "node_labels": ["service"],
            "message": "search graph",
        }
    )

    client.entity_by_label_search.assert_awaited_once_with(
        "nginx",
        node_labels=["service"],
    )
    assert "Entities:" in result
    assert "nginx" in result
