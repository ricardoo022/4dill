from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from pentest.agents.scanner import ScannerError, create_scanner_graph, run_scanner
from pentest.models.hack import HackResult


@pytest.mark.asyncio
@pytest.mark.agent
async def test_create_scanner_graph_minimal():
    llm = MagicMock()
    docker_client = MagicMock()
    container_id = "test-container"

    graph = await create_scanner_graph(
        llm=llm, docker_client=docker_client, container_id=container_id
    )
    assert graph is not None


@pytest.mark.asyncio
@pytest.mark.agent
async def test_run_scanner_happy_path(monkeypatch):
    # Mock LLM and graph invocation
    mock_llm = MagicMock()

    mock_result = {
        "messages": [AIMessage(content="Thinking...")],
        "barrier_hit": True,
        "barrier_result": {"result": "Vulnerability found: XSS", "message": "Found XSS on /search"},
    }

    # We need to mock the graph.ainvoke
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=mock_result)

    # create_agent_graph is NOT a coroutine, so we use a regular mock or lambda
    monkeypatch.setattr("pentest.agents.scanner.create_agent_graph", lambda **k: mock_graph)
    monkeypatch.setattr("pentest.agents.scanner._resolve_scanner_llm", lambda **k: mock_llm)

    docker_client = MagicMock()

    res = await run_scanner(
        question="Find XSS",
        docker_client=docker_client,
        container_id="test-container",
        docker_image="kali",
        cwd="/work",
    )

    assert isinstance(res, HackResult)
    assert res.result == "Vulnerability found: XSS"
    assert res.message == "Found XSS on /search"


@pytest.mark.asyncio
@pytest.mark.agent
async def test_run_scanner_no_barrier(monkeypatch):
    mock_llm = MagicMock()
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"messages": [], "barrier_hit": False})

    monkeypatch.setattr("pentest.agents.scanner.create_agent_graph", lambda **k: mock_graph)
    monkeypatch.setattr("pentest.agents.scanner._resolve_scanner_llm", lambda **k: mock_llm)

    docker_client = MagicMock()

    with pytest.raises(ScannerError, match="Scanner failed to return a hack_result"):
        await run_scanner(
            question="Find XSS",
            docker_client=docker_client,
            container_id="test-container",
            docker_image="kali",
        )
