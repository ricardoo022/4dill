from unittest.mock import MagicMock

from langchain_core.language_models.chat_models import BaseChatModel

from pentest.tools.adviser import create_advice_tool


def test_create_advice_tool():
    """Tests that advice tool is created with correct metadata and schema."""
    mock_llm = MagicMock(spec=BaseChatModel)
    tool = create_advice_tool(mock_llm)

    assert tool.name == "advice"
    assert "strategic guidance" in tool.description
    assert tool.args_schema is not None
    # Check schema fields
    schema = tool.args_schema.model_json_schema()
    assert "question" in schema["properties"]
    assert "context" in schema["properties"]
    assert "execution_context" in schema["properties"]
