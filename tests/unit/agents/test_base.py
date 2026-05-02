from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from pentest.agents.base import create_agent_graph


@tool
def dummy_tool(query: str) -> str:
    """A normal dummy tool."""
    return "dummy result"


@tool
def barrier_tool(plan: str) -> str:
    """A barrier tool."""
    return "barrier processed"


def test_graph_no_tools_to_end():
    """Test: LLM returns text (no tools) -> END, result is None"""
    mock_llm = RunnableLambda(lambda x: AIMessage(content="I am done, no tools needed."))
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [dummy_tool, barrier_tool], barrier_names=["barrier_tool"])
    result = graph.invoke({"messages": [HumanMessage(content="Hello")]})

    assert not result.get("barrier_hit")
    assert result.get("barrier_result") is None
    assert len(result["messages"]) == 2  # Human + AI


def test_graph_barrier_first_turn():
    """Test: Barrier on first turn -> stops, result extracted"""
    mock_llm = RunnableLambda(
        lambda x: AIMessage(
            content="",
            tool_calls=[{"name": "barrier_tool", "args": {"plan": "direct plan"}, "id": "call_1"}],
        )
    )
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [dummy_tool, barrier_tool], barrier_names=["barrier_tool"])
    result = graph.invoke({"messages": [HumanMessage(content="Make a plan")]})

    assert result.get("barrier_hit") is True
    assert result["barrier_result"] == {"plan": "direct plan"}
    assert len(result["messages"]) == 3  # Human, AI, ToolMessage


def test_graph_multiple_turns():
    """Test: Multiple turns: tool A -> tool B (barrier) -> stop"""
    call_count = 0

    def fake_llm_logic(msgs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "dummy_tool", "args": {"query": "test"}, "id": "call_1"}],
            )
        else:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "barrier_tool", "args": {"plan": "final plan"}, "id": "call_2"}
                ],
            )

    mock_llm = RunnableLambda(fake_llm_logic)
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [dummy_tool, barrier_tool], barrier_names=["barrier_tool"])
    result = graph.invoke({"messages": [HumanMessage(content="Do multi-step")]})

    assert result.get("barrier_hit") is True
    assert result["barrier_result"] == {"plan": "final plan"}
    assert call_count == 2
    assert len(result["messages"]) == 5  # Human, AI(tool), ToolMsg, AI(barrier), ToolMsg
