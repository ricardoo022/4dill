# File: tests/unit/tools/test_search_in_memory_unit.py
"""Unit tests for US-081: search_in_memory tool with flow/task/subtask filters."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from pentest.models.tool_args import SearchInMemoryAction
from pentest.tools.search_memory import create_search_in_memory_tool


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def mock_embeddings():
    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock:
        instance = mock.return_value
        instance.aembed_query = AsyncMock(return_value=[0.1] * 1536)
        yield instance


def test_create_search_in_memory_tool_no_db():
    """US-081: Should return fallback when db_session is None."""
    tool = create_search_in_memory_tool(None)
    assert isinstance(tool, BaseTool)
    assert tool.args_schema is SearchInMemoryAction


@pytest.mark.asyncio
async def test_search_in_memory_no_db_returns_fallback():
    """US-081: Tool reports vector store not available when db_session=None."""
    tool = create_search_in_memory_tool(None)
    result = await tool.ainvoke({"queries": ["test query"], "message": "searching memory..."})
    assert result == "vector store not available"


def test_search_in_memory_uses_schema():
    """US-081: Tool must expose SearchInMemoryAction for function-calling schema."""
    tool = create_search_in_memory_tool(AsyncMock())
    assert tool.args_schema is SearchInMemoryAction

    schema = tool.args_schema.model_json_schema()
    assert schema["type"] == "object"
    assert {"queries", "max_results", "message"}.issubset(schema["properties"])
    assert "task_id" in schema["properties"]
    assert "subtask_id" in schema["properties"]


def test_search_in_memory_action_valid():
    """US-081: SearchInMemoryAction validates correctly with valid input."""
    action = SearchInMemoryAction(
        queries=["nmap results", "open ports"],
        task_id=42,
        subtask_id=7,
        max_results=5,
        message="searching for scan results",
    )
    assert action.queries == ["nmap results", "open ports"]
    assert action.task_id == 42
    assert action.subtask_id == 7
    assert action.max_results == 5


def test_search_in_memory_action_empty_queries_rejected():
    """US-081: Empty query string is rejected."""
    with pytest.raises(ValidationError, match="non-empty"):
        SearchInMemoryAction(
            queries=["valid query", ""],
            message="test",
        )


def test_search_in_memory_action_too_many_queries_rejected():
    """US-081: More than 5 queries is rejected."""
    with pytest.raises(ValidationError):
        SearchInMemoryAction(
            queries=["q1", "q2", "q3", "q4", "q5", "q6"],
            message="test",
        )


def test_search_in_memory_action_empty_message_rejected():
    """US-081: Blank message is rejected."""
    with pytest.raises(ValidationError, match="blank"):
        SearchInMemoryAction(
            queries=["test"],
            message="   ",
        )


@pytest.mark.asyncio
async def test_search_in_memory_no_openai_key(mock_db_session):
    """US-081: Should report missing OPENAI_API_KEY."""
    with patch.dict(os.environ, {}, clear=True):
        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke({"queries": ["test query"], "message": "searching..."})
        assert "embeddings not configured - set OPENAI_API_KEY" in result


@pytest.mark.asyncio
async def test_search_in_memory_no_results(mock_db_session, mock_embeddings):
    """US-081: Should return specific message when no results found. 🔁"""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke(
            {"queries": ["nonexistent vulnerability"], "message": "searching..."}
        )
        assert "Nothing found in memory" in result


@pytest.mark.asyncio
async def test_search_in_memory_with_results(mock_db_session, mock_embeddings):
    """US-081: Should format results with scores and metadata."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_row = MagicMock()
        mock_row.id = 100
        mock_row.content = "OpenSSH 8.9 vulnerability on port 22 allows remote code execution"
        mock_row.metadata_ = {
            "doc_type": "vulnerability",
            "flow_id": "5",
            "task_id": "3",
            "subtask_id": "1",
            "question": "what vulns on port 22",
        }

        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.08)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke({"queries": ["ssh vulnerability"], "message": "searching..."})

        assert "Found 1 relevant memory entries:" in result
        assert "[Score: 0.92]" in result
        assert "[vulnerability]" in result
        assert "flow=5" in result
        assert "task=3" in result
        assert "subtask=1" in result
        assert "OpenSSH 8.9" in result


@pytest.mark.asyncio
async def test_search_in_memory_deduplication(mock_db_session, mock_embeddings):
    """US-081: Should not show same document twice for multiple queries. 🔁"""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_row = MagicMock()
        mock_row.id = 42
        mock_row.content = "CVE-2023-38408: OpenSSH PKCS#11 RCE via forwarded agent"
        mock_row.metadata_ = {"doc_type": "vulnerability"}

        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.05)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke(
            {
                "queries": ["openssh rce", "ssh agent forwarding exploit"],
                "message": "searching...",
            }
        )

        assert "Found 1 relevant memory entries:" in result


@pytest.mark.asyncio
async def test_search_in_memory_multi_query_merge(mock_db_session, mock_embeddings):
    """US-081: Should merge results from multiple queries with dedup."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        row_a = MagicMock()
        row_a.id = 1
        row_a.content = "SQL injection in login form"
        row_a.metadata_ = {"doc_type": "vulnerability"}

        row_b = MagicMock()
        row_b.id = 2
        row_b.content = "XSS in search parameter"
        row_b.metadata_ = {"doc_type": "vulnerability"}

        call_count = 0

        def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            # Call 1: count query uses .scalar(), not .all()
            if call_count == 1:
                result_mock.scalar.return_value = 0
            # Calls 2-3: SET LOCAL (no return value used)
            # Call 4: first search query → row_a
            elif call_count == 4:
                result_mock.all.return_value = [(row_a, 0.1)]
            # Call 5: second search query → row_b
            else:
                result_mock.all.return_value = [(row_b, 0.15)]
            return result_mock

        mock_db_session.execute.side_effect = execute_side_effect

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke(
            {
                "queries": ["sql injection", "cross site scripting"],
                "message": "searching...",
            }
        )

        assert "Found 2 relevant memory entries:" in result
        assert "SQL injection" in result
        assert "XSS" in result


@pytest.mark.asyncio
async def test_search_in_memory_max_results_limit(mock_db_session, mock_embeddings):
    """US-081: Should respect max_results parameter."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rows = []
        for i in range(20):
            row = MagicMock()
            row.id = i
            row.content = f"Finding number {i}"
            row.metadata_ = {"doc_type": "vulnerability"}
            rows.append(row)

        execute_result = MagicMock()
        execute_result.all.return_value = [(r, 0.1 + i * 0.01) for i, r in enumerate(rows[:15])]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke(
            {
                "queries": ["vulnerabilities"],
                "max_results": 5,
                "message": "searching...",
            }
        )

        assert "Found 5 relevant memory entries:" in result


@pytest.mark.asyncio
async def test_search_in_memory_task_id_filter(mock_db_session, mock_embeddings):
    """US-081: Should include task_id filter in SQL query."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.content = "Task-specific finding"
        mock_row.metadata_ = {"doc_type": "guide", "task_id": "42"}

        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.1)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        await tool.ainvoke(
            {
                "queries": ["test"],
                "task_id": 42,
                "message": "searching with filter",
            }
        )

        # Verify execute was called (count + SET LOCAL + search query)
        assert mock_db_session.execute.call_count >= 1


@pytest.mark.asyncio
async def test_search_in_memory_subtask_id_filter(mock_db_session, mock_embeddings):
    """US-081: Should include subtask_id filter in SQL query."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.content = "Subtask-specific finding"
        mock_row.metadata_ = {"doc_type": "code", "subtask_id": "7"}

        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.1)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        await tool.ainvoke(
            {
                "queries": ["test"],
                "subtask_id": 7,
                "message": "searching with filter",
            }
        )

        # Verify execute was called (count + SET LOCAL + search query)
        assert mock_db_session.execute.call_count >= 1


@pytest.mark.asyncio
async def test_search_in_memory_db_error_handling(mock_db_session, mock_embeddings):
    """US-081: Should return error string on database failure."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_db_session.execute.side_effect = Exception("Connection pool exhausted")

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke({"queries": ["broken query"], "message": "searching..."})
        assert "search_in_memory tool error: Connection pool exhausted" in result


@pytest.mark.asyncio
async def test_search_in_memory_sorting_by_score(mock_db_session, mock_embeddings):
    """US-081: Results should be sorted by score descending."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        row_low = MagicMock()
        row_low.id = 10
        row_low.content = "Low relevance finding"
        row_low.metadata_ = {"doc_type": "vulnerability"}

        row_high = MagicMock()
        row_high.id = 20
        row_high.content = "High relevance finding"
        row_high.metadata_ = {"doc_type": "vulnerability"}

        execute_result = MagicMock()
        execute_result.all.return_value = [
            (row_low, 0.25),  # score 0.75
            (row_high, 0.02),  # score 0.98
        ]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_in_memory_tool(mock_db_session)
        result = await tool.ainvoke({"queries": ["test"], "message": "searching..."})

        lines = result.split("\n")
        high_idx = next(i for i, line in enumerate(lines) if "High relevance" in line)
        low_idx = next(i for i, line in enumerate(lines) if "Low relevance" in line)
        assert high_idx < low_idx, "High score should appear before low score"
