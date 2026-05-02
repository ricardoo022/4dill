# File: tests/unit/tools/test_search_memory.py
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from pentest.models.search import SearchAnswerAction
from pentest.tools.search_memory import create_search_answer_tool


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def mock_embeddings():
    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock:
        instance = mock.return_value
        # Mock aembed_query to return a dummy vector
        instance.aembed_query = AsyncMock(return_value=[0.1] * 1536)
        yield instance


@pytest.mark.asyncio
async def test_create_search_answer_tool_no_db():
    """US-058: Should return a tool that reports vector store not available."""
    tool = create_search_answer_tool(None)
    assert isinstance(tool, BaseTool)
    result = await tool.ainvoke({"questions": ["test"], "type": "guide", "message": "searching..."})
    assert result == "vector store not available"


def test_search_answer_tool_uses_search_answer_action_schema():
    """US-058: Tool must expose SearchAnswerAction for function-calling schema."""
    tool = create_search_answer_tool(AsyncMock())
    assert tool.args_schema is SearchAnswerAction

    schema = tool.args_schema.model_json_schema()
    assert schema["type"] == "object"
    assert {"questions", "type", "message"}.issubset(schema["properties"])


@pytest.mark.asyncio
async def test_search_answer_no_openai_key(mock_db_session):
    """US-058: Should report missing OPENAI_API_KEY."""
    with patch.dict(os.environ, {}, clear=True):
        tool = create_search_answer_tool(mock_db_session)
        result = await tool.ainvoke(
            {"questions": ["test"], "type": "guide", "message": "searching..."}
        )
        assert "embeddings not configured - set OPENAI_API_KEY" in result


@pytest.mark.asyncio
async def test_search_answer_no_results(mock_db_session, mock_embeddings):
    """US-058: Should return specific message when no results found."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        # Mock session execute to return an empty result set
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db_session.execute.return_value = execute_result

        tool = create_search_answer_tool(mock_db_session)
        result = await tool.ainvoke(
            {"questions": ["test query"], "type": "guide", "message": "searching..."}
        )
        assert "Nothing found in answer store for these queries" in result


@pytest.mark.asyncio
async def test_search_answer_with_results(mock_db_session, mock_embeddings):
    """US-058: Should format results correctly with scores and metadata."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        # Mock VectorStore row
        mock_row = MagicMock()
        mock_row.id = 123
        mock_row.content = "Confirmed SQL injection in login form via 'username' parameter."
        mock_row.metadata_ = {"question": "how to find sqli in login"}

        # Return row with distance 0.1 (Score 0.90)
        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.1)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_answer_tool(mock_db_session)
        result = await tool.ainvoke(
            {"questions": ["sqli login"], "type": "vulnerability", "message": "searching..."}
        )

        assert "Found 1 relevant answers:" in result
        assert "[Score: 0.90]" in result
        assert 'Q: "how to find sqli in login"' in result
        assert "A: Confirmed SQL injection" in result


@pytest.mark.asyncio
async def test_search_answer_deduplication(mock_db_session, mock_embeddings):
    """US-058: Should not show the same document twice for multiple queries."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_row = MagicMock()
        mock_row.id = 42
        mock_row.content = "Unique content"
        mock_row.metadata_ = {"question": "Shared question"}

        # Same row returned for both queries
        execute_result = MagicMock()
        execute_result.all.return_value = [(mock_row, 0.05)]
        mock_db_session.execute.return_value = execute_result

        tool = create_search_answer_tool(mock_db_session)
        result = await tool.ainvoke(
            {"questions": ["query 1", "query 2"], "type": "code", "message": "searching..."}
        )

        # Should only find 1 answer despite 2 queries
        assert "Found 1 relevant answers:" in result


@pytest.mark.asyncio
async def test_search_answer_db_error_handling(mock_db_session, mock_embeddings):
    """US-058: Should return error string on database failure."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        mock_db_session.execute.side_effect = Exception("Connection lost")

        tool = create_search_answer_tool(mock_db_session)
        result = await tool.ainvoke(
            {"questions": ["broken"], "type": "other", "message": "searching..."}
        )
        assert "search_answer tool error: Connection lost" in result
