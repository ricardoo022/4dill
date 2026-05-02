from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from pentest.agents.scanner import ScannerError, create_scanner_graph, run_scanner
from pentest.models.hack import HackResult


@pytest.mark.agent
async def test_create_scanner_graph_minimal():
    llm = MagicMock()
    docker_client = MagicMock()
    container_id = "test-container"

    graph = await create_scanner_graph(
        llm=llm, docker_client=docker_client, container_id=container_id
    )
    assert graph is not None


@pytest.mark.agent
async def test_create_scanner_graph_requires_installer_and_not_maintenance(monkeypatch):
    llm = MagicMock()
    docker_client = MagicMock()
    captured: dict[str, object] = {}

    def fake_create_agent_graph(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr("pentest.agents.scanner.create_agent_graph", fake_create_agent_graph)

    await create_scanner_graph(
        llm=llm,
        docker_client=docker_client,
        container_id="test-container",
    )

    tool_names = {getattr(t, "name", "") for t in captured["tools"]}
    assert "installer" in tool_names
    assert "maintenance" not in tool_names


@pytest.mark.agent
async def test_create_scanner_graph_fails_when_required_tool_missing(monkeypatch):
    llm = MagicMock()
    docker_client = MagicMock()

    monkeypatch.setattr("pentest.agents.scanner.searcher", None)

    with pytest.raises(ScannerError, match="Missing required Scanner tools"):
        await create_scanner_graph(
            llm=llm,
            docker_client=docker_client,
            container_id="test-container",
        )


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


@pytest.mark.agent
async def test_run_scanner_passes_fase_to_prompt_renderer(monkeypatch):
    mock_llm = MagicMock()
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [AIMessage(content="done")],
            "barrier_hit": True,
            "barrier_result": {"result": "ok", "message": "ok"},
        }
    )
    captured: dict[str, object] = {}

    def fake_render_scanner_prompt(**kwargs):
        captured.update(kwargs)
        return ("system", "user")

    monkeypatch.setattr("pentest.agents.scanner.create_agent_graph", lambda **k: mock_graph)
    monkeypatch.setattr("pentest.agents.scanner._resolve_scanner_llm", lambda **k: mock_llm)
    monkeypatch.setattr("pentest.agents.scanner.render_scanner_prompt", fake_render_scanner_prompt)

    docker_client = MagicMock()

    await run_scanner(
        question="Find XSS",
        docker_client=docker_client,
        container_id="test-container",
        docker_image="kali",
        fase="fase-1",
        skills_dir="/tmp/skills",
    )

    assert captured["fase"] == "fase-1"
    assert captured["skills_dir"] == "/tmp/skills"
