import os

import pytest

from pentest.agents.adviser import give_advice
from pentest.providers.factory import create_chat_model


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"),
    reason="Missing LLM API keys for E2E test",
)
async def test_adviser_real_chain():
    """Tests the full adviser chain with a real LLM."""
    # Use the default provider/model for the adviser
    llm = create_chat_model(agent_name="adviser")

    question = (
        "What is the best way to test for blind SQL injection in a JSON body field 'user_id'?"
    )
    context = "I found a POST endpoint /api/profile that takes JSON. No errors are returned, but the response time varies slightly."

    response = await give_advice(question=question, context=context, llm=llm)

    assert isinstance(response, str)
    assert len(response) > 50
    # Expect some strategic keywords
    response_lower = response.lower()
    assert any(
        word in response_lower for word in ["sleep", "waitfor", "benchmark", "time", "boolean"]
    )
    assert "user_id" in response_lower
