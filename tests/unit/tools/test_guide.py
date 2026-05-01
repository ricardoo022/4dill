import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from pentest.models.tool_args import SearchGuideAction, StoreGuideAction
from pentest.tools.guide import _anonymize_content, create_guide_tools, is_available


def test_is_available():
    """Test is_available check."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        assert is_available() is True

    with patch.dict(os.environ, {}, clear=True):
        assert is_available() is False


def test_anonymize_content():
    """Test masking of sensitive data."""
    raw = "Target IP is 192.168.1.10. Use password: admin_secret and key='AKIA-TEST'."
    anonymized = _anonymize_content(raw)

    assert "192.168.1.10" not in anonymized
    assert "[IP]" in anonymized
    assert "admin_secret" not in anonymized
    assert "password: [REDACTED]" in anonymized
    assert "AKIA-TEST" not in anonymized
    assert "key: [REDACTED]" in anonymized

    # Test URL credentials
    url_raw = "Connect to http://admin:p4ssw0rd@10.0.0.1/api"
    url_anon = _anonymize_content(url_raw)
    assert "admin:p4ssw0rd" not in url_anon
    assert "http://[USER]:[PASS]@[IP]/api" in url_anon


def test_guide_actions_validation():
    """Test Pydantic validation for guide actions."""
    # Invalid Search: empty questions
    with pytest.raises(ValidationError):
        SearchGuideAction(questions=[], type="pentest", message="test")

    # Invalid Search: too many questions
    with pytest.raises(ValidationError):
        SearchGuideAction(questions=["q"] * 6, type="pentest", message="test")

    # Invalid Search: wrong category
    with pytest.raises(ValidationError):
        SearchGuideAction(questions=["q"], type="wrong", message="test")

    # Invalid Store: too short guide
    with pytest.raises(ValidationError):
        StoreGuideAction(
            guide="too short", question="Valid question?", type="pentest", message="test"
        )


@pytest.mark.asyncio
async def test_search_guide_nothing_found():
    """Test search_guide when no results are found."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(all=lambda: [])

    search_tool, _ = create_guide_tools(mock_session)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
        "langchain_openai.OpenAIEmbeddings.aembed_query", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = [0.1] * 1536
        result = await search_tool.arun(
            {"questions": ["how to bypass waf"], "type": "pentest", "message": "searching"}
        )
        assert "nothing found in guide store" in result


@pytest.mark.asyncio
async def test_search_guide_merge_and_deduplicate():
    """Test merging results from multiple queries and deduplication."""
    mock_session = AsyncMock()

    # Create mock rows
    row1 = MagicMock(id=1, content="Guide 1 content", metadata_={"question": "WAF bypass"})
    row2 = MagicMock(id=2, content="Guide 2 content", metadata_={"question": "SQLi methodology"})

    # First query returns row1 and row2
    # Second query returns row1 (with higher score)
    mock_result_1 = MagicMock()
    mock_result_1.all.return_value = [
        (row1, 0.1),
        (row2, 0.15),
    ]  # Distance 0.1 -> Score 0.9, Distance 0.15 -> Score 0.85

    mock_result_2 = MagicMock()
    mock_result_2.all.return_value = [(row1, 0.05)]  # Distance 0.05 -> Score 0.95

    mock_session.execute.side_effect = [mock_result_1, mock_result_2]

    search_tool, _ = create_guide_tools(mock_session)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
        "langchain_openai.OpenAIEmbeddings.aembed_query", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = [0.1] * 1536
        result = await search_tool.arun(
            {"questions": ["q1", "q2"], "type": "pentest", "message": "searching"}
        )

        # Check result contains both but unique
        assert "Found 2 relevant guides" in result
        assert '[Score: 0.95] Q: "WAF bypass"' in result  # Higher score from second query
        assert '[Score: 0.85] Q: "SQLi methodology"' in result


@pytest.mark.asyncio
async def test_store_guide_success():
    """Test successful storage of a guide."""
    mock_session = AsyncMock()
    _, store_tool = create_guide_tools(mock_session)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
        "langchain_openai.OpenAIEmbeddings.aembed_query", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = [0.1] * 1536
        result = await store_tool.arun(
            {
                "guide": "Detailed methodology for attacking 192.168.1.1",
                "question": "How to attack local network?",
                "type": "pentest",
                "message": "storing new guide",
                "flow_id": "flow-123",
                "task_id": "task-456",
            }
        )

        assert result == "guide stored successfully"
        assert mock_session.add.called
        assert mock_session.commit.called

        # Verify anonymization before storage
        added_vector = mock_session.add.call_args[0][0]
        assert "192.168.1.1" not in added_vector.content
        assert "[IP]" in added_vector.content
        assert "Question:\nHow to attack local network?" in added_vector.content
        assert added_vector.metadata_["flow_id"] == "flow-123"
        assert added_vector.metadata_["task_id"] == "task-456"
        assert added_vector.metadata_["guide_type"] == "pentest"
