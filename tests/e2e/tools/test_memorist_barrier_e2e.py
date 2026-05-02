import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from pentest.agents.base import create_agent_graph
from pentest.tools.barriers import memorist_result
from pentest.tools.stubs import memorist

pytestmark = pytest.mark.e2e


def _mock_memorist_llm(messages):
    has_tool_response = any(isinstance(message, ToolMessage) for message in messages)

    if not has_tool_response:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "memorist",
                    "args": {
                        "question": "Check previous findings for CVE-2024-0001",
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
                    "result": "CVE-2024-0001 was previously detected on host 10.0.0.15",
                    "message": "Memory lookup completed",
                },
                "id": "call_memorist_result",
            }
        ],
    )


def test_memorist_result_barrier_end_to_end():
    llm = RunnableLambda(_mock_memorist_llm)
    llm.bind_tools = lambda tools: llm

    graph = create_agent_graph(
        llm,
        [memorist, memorist_result],
        barrier_names=["memorist_result"],
    )

    result = graph.invoke(
        {"messages": [HumanMessage(content="Summarize prior memory for this CVE")]}
    )

    assert result.get("barrier_hit") is True
    assert result["barrier_result"] == {
        "result": "CVE-2024-0001 was previously detected on host 10.0.0.15",
        "message": "Memory lookup completed",
    }

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(tool_messages) == 2
    assert tool_messages[-1].content == "memorist result successfully processed"
