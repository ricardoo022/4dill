from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from pentest.agents.generator import GeneratorError, generate_subtasks
from pentest.models.recon import BackendProfile

pytestmark = pytest.mark.agent


class _FakeGraph:
    def __init__(self, result: dict[str, Any]):
        self._result = result

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        assert "messages" in state
        return self._result


class _FakeLLM:
    def bind_tools(self, tools):  # noqa: ANN001
        return self

    def invoke(self, _state):  # noqa: ANN001
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subtask_list",
                    "args": {
                        "subtasks": [
                            {
                                "title": "Map API surface",
                                "description": "Enumerate public endpoints and auth requirements.",
                                "fase": "fase-1",
                            },
                            {
                                "title": "Test auth bypass",
                                "description": "Probe RLS/Auth controls on discovered endpoints.",
                                "fase": "fase-3",
                            },
                        ],
                        "message": "plan completed",
                    },
                    "id": "call_subtasks",
                }
            ],
        )


async def test_generate_subtasks_agent_happy_path_with_realistic_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔁 Generates a realistic Supabase plan and validates generator output contract."""
    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3"],
        configs={"url": "https://abc.supabase.co"},
        subdomains=[],
    )

    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, backend_profile, fase_index, execution_context: ("system", "user"),
    )

    mock_llm = _FakeLLM()
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: mock_llm)

    subtasks = await generate_subtasks("scan https://example.com", profile, "/tmp/skills")

    assert 1 <= len(subtasks) <= 15
    assert all(item.title for item in subtasks)
    assert all(item.description for item in subtasks)
    assert any(item.fase for item in subtasks)


async def test_generate_subtasks_toolset_selection_with_and_without_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Includes terminal/file tools only when docker_client is provided."""
    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3", "fase-10"],
        configs={"url": "https://abc.supabase.co"},
        subdomains=[],
    )
    captured_tools: dict[str, list[str]] = {}
    call_index = {"value": 0}

    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, backend_profile, fase_index, execution_context: ("system", "user"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: _FakeLLM())

    def _fake_create_graph(llm, tools, barrier_names, max_iterations):
        key = "without_docker" if call_index["value"] == 0 else "with_docker"
        captured_tools[key] = [tool.name for tool in tools]
        call_index["value"] += 1
        return _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [
                        {
                            "title": "Map attack surface",
                            "description": "Run nmap -sV and crawl /api endpoints for exposure.",
                            "fase": "fase-1",
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr("pentest.agents.generator.create_agent_graph", _fake_create_graph)

    await generate_subtasks("scan https://example.com", profile, "/tmp/skills", docker_client=None)

    class _DockerMock:
        def exec_command(self, container_id, input, cwd, timeout, detach):  # noqa: A002
            return "Starting Nmap 7.94\n80/tcp open http\n443/tcp open https\n"

        def read_file(self, container_id, path):
            return "CVE-2024-12345 candidate in auth middleware"

        def write_file(self, container_id, path, content):
            return f"wrote {len(content)} bytes"

    await generate_subtasks(
        "scan https://example.com",
        profile,
        "/tmp/skills",
        docker_client=_DockerMock(),  # type: ignore[arg-type]
    )

    assert "terminal" not in captured_tools["without_docker"]
    assert "file" not in captured_tools["without_docker"]
    assert "terminal" in captured_tools["with_docker"]
    assert "file" in captured_tools["with_docker"]


async def test_generate_subtasks_raises_generator_error_when_barrier_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raises explicit GeneratorError when the agent loop ends without subtask_list barrier."""
    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3"],
        configs={"url": "https://abc.supabase.co"},
        subdomains=[],
    )

    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, backend_profile, fase_index, execution_context: ("system", "user"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: _FakeLLM())
    monkeypatch.setattr(
        "pentest.agents.generator.create_agent_graph",
        lambda llm, tools, barrier_names, max_iterations: _FakeGraph(
            {"barrier_hit": False, "barrier_result": None}
        ),
    )

    with pytest.raises(GeneratorError, match="Generator failed to produce a plan"):
        await generate_subtasks("scan https://example.com", profile, "/tmp/skills")
