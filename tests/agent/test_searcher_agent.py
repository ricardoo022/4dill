"""Agent-layer tests for the Searcher agent."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from pentest.agents.generator import generate_subtasks
from pentest.agents.searcher import SearcherError, create_searcher_tool, perform_search
from pentest.models.recon import BackendProfile


@pytest.mark.agent
async def test_perform_search_success():
    """
    Tests: AC "perform_search renders prompt, mounts tools, creates graph, extracts result".
    Round-trip: input -> tool node -> llm node -> barrier node -> final result string.
    """
    mock_llm = MagicMock()

    # 1. LLM decides to call duckduckgo
    msg1 = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "duckduckgo",
                "args": {"query": "nginx 1.24 vulnerabilities", "message": "searching..."},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    # 2. LLM receives tool output and calls search_result barrier
    msg2 = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {
                    "result": "Found CVE-2024-5678: Nginx 1.24 path traversal vulnerability confirmed by several sources.",
                    "message": "Research complete.",
                },
                "id": "call_2",
                "type": "tool_call",
            }
        ],
    )

    mock_llm.bind_tools.return_value.invoke.side_effect = [msg1, msg2]

    # Mock is_available to ensure DDG is included
    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
    ):
        result = await perform_search(question="nginx 1.24 vulnerabilities", llm=mock_llm)

    assert "CVE-2024-5678" in result
    assert "path traversal" in result
    assert mock_llm.bind_tools.return_value.invoke.call_count == 2


@pytest.mark.agent
async def test_perform_search_no_engines():
    """
    Tests: AC "Return 'No search engines available...' immediately if neither DDG nor Tavily are available".
    """
    mock_llm = MagicMock()

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=False),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
    ):
        result = await perform_search(question="What is the capital of France?", llm=mock_llm)

    assert "No search engines available" in result
    # Should return early without calling LLM
    mock_llm.bind_tools.assert_not_called()


@pytest.mark.agent
async def test_perform_search_failure_no_barrier():
    """
    Tests: AC "Raise SearcherError if barrier is not called".
    """
    mock_llm = MagicMock()

    # LLM just chats without calling tools
    msg = AIMessage(content="I am thinking about it but I won't call the barrier.")
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        pytest.raises(SearcherError, match="Searcher failed to produce a result"),
    ):
        await perform_search(question="Why is the sky blue?", llm=mock_llm)


@pytest.mark.agent
async def test_create_searcher_tool_async():
    """
    Tests: AC "create_searcher_tool creates an async LangChain tool... never raises errors to the LLM".
    """
    mock_llm = MagicMock()

    # Tool that fails internally
    with patch(
        "pentest.agents.searcher.perform_search", side_effect=Exception("Internal Network Error")
    ):
        search_tool = create_searcher_tool(llm=mock_llm)

        # Invoke tool (it should be async)
        result = await search_tool.ainvoke({"question": "test", "message": "test"})

    assert "Searcher error: Internal Network Error" in result


@pytest.mark.agent
async def test_perform_search_includes_search_answer_with_db_session_and_openai_key():
    mock_llm = MagicMock()
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {"result": "ok", "message": "done"},
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    @tool
    def search_answer(question: str) -> str:
        """Search memorized answers."""
        return f"answer for {question}"

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
        patch("pentest.agents.searcher.create_search_answer_tool") as mock_search_answer_tool,
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False),
    ):
        mock_search_answer_tool.return_value = search_answer
        await perform_search(question="nginx cve", llm=mock_llm, db_session=MagicMock())

    tools_called = mock_llm.bind_tools.call_args[0][0]
    tool_names = [getattr(t, "name", "") for t in tools_called]
    assert "search_answer" in tool_names


@pytest.mark.agent
async def test_perform_search_excludes_search_answer_without_db_session():
    mock_llm = MagicMock()
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {"result": "ok", "message": "done"},
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False),
    ):
        await perform_search(question="nginx cve", llm=mock_llm, db_session=None)

    tools_called = mock_llm.bind_tools.call_args[0][0]
    tool_names = [getattr(t, "name", "") for t in tools_called]
    assert "search_answer" not in tool_names


@pytest.mark.agent
async def test_perform_search_tavily_included_when_available():
    mock_llm = MagicMock()
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {"result": "ok", "message": "done"},
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=False),
        patch("pentest.agents.searcher.is_tavily_available", return_value=True),
    ):
        await perform_search(question="nginx cve", llm=mock_llm)

    tools_called = mock_llm.bind_tools.call_args[0][0]
    tool_names = [getattr(t, "name", "") for t in tools_called]
    assert "tavily_search" in tool_names


@pytest.mark.agent
async def test_perform_search_tavily_excluded_when_unavailable():
    mock_llm = MagicMock()
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {"result": "ok", "message": "done"},
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
    ):
        await perform_search(question="nginx cve", llm=mock_llm)

    tools_called = mock_llm.bind_tools.call_args[0][0]
    tool_names = [getattr(t, "name", "") for t in tools_called]
    assert "tavily_search" not in tool_names


@pytest.mark.agent
async def test_generator_integration():
    """
    Tests: AC "agents/generator.py must use the new tool".
    Verifies that generate_subtasks includes the Searcher tool and can trigger it.
    """
    # Mocking create_chat_model to return a mock LLM
    mock_llm = MagicMock()

    # Mock Generator calling subtask_list barrier
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "subtask_list",
                "args": {
                    "subtasks": [
                        {
                            "title": "Task 1",
                            "description": "Desc",
                            "fase": "1",
                            "task": "Task",
                            "subtask": "Sub",
                        }
                    ],
                    "message": "Plan ready",
                },
                "id": "gen_1",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="custom",
        confidence="high",
        scan_path=["phase0"],
    )

    with (
        patch("pentest.agents.generator.create_chat_model", return_value=mock_llm),
        patch("pentest.agents.generator.load_fase_index", return_value="index"),
        patch("pentest.agents.generator.render_generator_prompt", return_value=("sys", "user")),
    ):
        await generate_subtasks(input="test", backend_profile=profile, skills_dir="/tmp")

    # Check that create_agent_graph was called with search tool (ComplexSearch schema)
    # We can inspect the tools passed to bind_tools
    tools_called = mock_llm.bind_tools.call_args[0][0]
    tool_names = [
        getattr(t, "name", t.__name__ if hasattr(t, "__name__") else str(t)) for t in tools_called
    ]

    assert "search" in tool_names
    # Verify it's not the stub (which is named 'searcher' in stubs.py but we named it 'search' in Searcher tool factory)
    search_tool = next(t for t in tools_called if getattr(t, "name", "") == "search")
    assert search_tool.args_schema.__name__ == "ComplexSearch"


@pytest.mark.agent
async def test_perform_search_creates_llm_from_searcher_env_when_not_provided():
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {"result": "ok", "message": "done"},
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_created_llm = MagicMock()
    mock_created_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
        patch(
            "pentest.agents.searcher.create_chat_model", return_value=mock_created_llm
        ) as mock_factory,
    ):
        await perform_search(question="nginx cve", llm=None)

    mock_factory.assert_called_once_with(provider=None, model=None, agent_name="searcher")


@pytest.mark.agent
async def test_perform_search_logs_tools_and_result_summary(caplog: pytest.LogCaptureFixture):
    caplog.set_level("INFO", logger="pentest.agents.searcher")
    mock_llm = MagicMock()
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_result",
                "args": {
                    "result": "Found relevant findings in sources for nginx CVEs.",
                    "message": "done",
                },
                "id": "call_result",
                "type": "tool_call",
            }
        ],
    )
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    with (
        patch("pentest.agents.searcher.is_ddg_available", return_value=True),
        patch("pentest.agents.searcher.is_tavily_available", return_value=False),
    ):
        await perform_search(question="nginx cve", llm=mock_llm)

    assert "available tools" in caplog.text.lower()
    assert "result summary" in caplog.text.lower()
