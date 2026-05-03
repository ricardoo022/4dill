from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from pentest.agents.adviser import give_advice


@pytest.mark.agent
async def test_give_advice_agent_flow():
    """Tests the give_advice function logic with a mocked LLM."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="Try using slow-scanning with --rate 1.")

    question = "WAF is blocking me."
    context = "403 Forbidden on /api"

    response = await give_advice(question=question, context=context, llm=mock_llm)

    assert response == "Try using slow-scanning with --rate 1."

    # Verify LLM was called with correct message types
    mock_llm.ainvoke.assert_called_once()
    messages = mock_llm.ainvoke.call_args[0][0]
    assert len(messages) == 2
    assert messages[0].type == "system"
    assert messages[1].type == "human"
    assert question in messages[1].content
    assert context in messages[1].content
