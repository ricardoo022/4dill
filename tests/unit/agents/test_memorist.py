from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from pentest.agents.memorist import create_memorist_agent


def _mock_memorist_llm(messages):
    has_tool_response = any(isinstance(message, ToolMessage) for message in messages)

    if not has_tool_response:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "memorist",
                    "args": {
                        "question": "Check previous scan findings for SQL injection",
                        "message": "Searching memory",
                    },
                    "id": "call_memorist_lookup",
                }
            ],
        )

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "memorist_result",
                "args": {
                    "result": "SQL injection finding exists on endpoint /search",
                    "message": "Memory lookup completed",
                },
                "id": "call_memorist_result",
            }
        ],
    )


def test_create_memorist_agent_uses_base_graph_contract():
    llm = RunnableLambda(_mock_memorist_llm)
    llm.bind_tools = lambda tools: llm

    graph = create_memorist_agent(llm)
    result = graph.invoke({"messages": [HumanMessage(content="Find previous SQLi findings")]})

    assert result.get("barrier_hit") is True
    assert result["barrier_result"] == {
        "result": "SQL injection finding exists on endpoint /search",
        "message": "Memory lookup completed",
    }

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(tool_messages) == 2
    assert tool_messages[0].content.startswith("No previous scan data available")
    assert tool_messages[-1].content == "memorist result successfully processed"
