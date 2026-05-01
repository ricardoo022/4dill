from __future__ import annotations

from typing import Any

import pytest

from pentest.agents.generator import GeneratorError, generate_subtasks
from pentest.models.recon import BackendProfile


class _FakeGraph:
    def __init__(self, result: dict[str, Any]):
        self._result = result

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        assert "messages" in state
        return self._result


@pytest.fixture
def backend_profile() -> BackendProfile:
    return BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3"],
        configs={"url": "https://abc.supabase.co"},
        subdomains=[],
    )


async def test_generate_subtasks_happy_path_validates_output(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: object())
    monkeypatch.setattr(
        "pentest.agents.generator.create_agent_graph",
        lambda llm, tools, barrier_names, max_iterations: _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [
                        {
                            "title": "  Recon  ",
                            "description": "  enumerate endpoints  ",
                            "fase": "fase-1",
                        },
                        {"title": "Auth checks", "description": "Check RLS policies", "fase": None},
                    ]
                },
            }
        ),
    )

    subtasks = await generate_subtasks("scan https://example.com", backend_profile, "/skills")

    assert len(subtasks) == 2
    assert subtasks[0].title == "Recon"
    assert subtasks[0].description == "enumerate endpoints"
    assert all(item.title for item in subtasks)
    assert all(item.description for item in subtasks)
    assert any(item.fase for item in subtasks)


async def test_generate_subtasks_without_docker_excludes_terminal_and_file(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: object())

    def _fake_create_graph(llm, tools, barrier_names, max_iterations):
        seen["tools"] = tools
        return _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [{"title": "Recon", "description": "Desc", "fase": "fase-1"}]
                },
            }
        )

    monkeypatch.setattr("pentest.agents.generator.create_agent_graph", _fake_create_graph)

    await generate_subtasks("scan", backend_profile, "/skills", docker_client=None)
    tool_names = {tool.name for tool in seen["tools"]}
    assert "terminal" not in tool_names
    assert "file" not in tool_names


async def test_generate_subtasks_with_docker_includes_terminal_and_file(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: object())

    def _fake_create_graph(llm, tools, barrier_names, max_iterations):
        seen["tools"] = tools
        return _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [{"title": "Recon", "description": "Desc", "fase": "fase-1"}]
                },
            }
        )

    monkeypatch.setattr("pentest.agents.generator.create_agent_graph", _fake_create_graph)

    class _DockerMock:
        def exec_command(self, container_id, input, cwd, timeout, detach):  # noqa: A002
            return "ok"

        def read_file(self, container_id, path):
            return "file"

        def write_file(self, container_id, path, content):
            return "written"

    await generate_subtasks("scan", backend_profile, "/skills", docker_client=_DockerMock())  # type: ignore[arg-type]
    tool_names = {tool.name for tool in seen["tools"]}
    assert "terminal" in tool_names
    assert "file" in tool_names


async def test_generate_subtasks_raises_when_no_barrier(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: object())
    monkeypatch.setattr(
        "pentest.agents.generator.create_agent_graph",
        lambda llm, tools, barrier_names, max_iterations: _FakeGraph(
            {"barrier_hit": False, "barrier_result": None}
        ),
    )

    with pytest.raises(GeneratorError, match="Generator failed to produce a plan"):
        await generate_subtasks("scan", backend_profile, "/skills")


async def test_generate_subtasks_model_resolution_param_over_env_and_default(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    captured_models: list[str] = []
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )

    class _FakeChatAnthropic:
        def __init__(self, **kwargs: Any):
            captured_models.append(kwargs["model_name"])

    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", _FakeChatAnthropic)
    monkeypatch.setattr(
        "pentest.agents.generator.create_agent_graph",
        lambda llm, tools, barrier_names, max_iterations: _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [{"title": "Recon", "description": "Desc", "fase": "fase-1"}]
                },
            }
        ),
    )

    monkeypatch.setenv("GENERATOR_MODEL", "env-model")
    await generate_subtasks("scan", backend_profile, "/skills", model="param-model")
    await generate_subtasks("scan", backend_profile, "/skills")
    monkeypatch.delenv("GENERATOR_MODEL")
    await generate_subtasks("scan", backend_profile, "/skills")

    assert captured_models == ["param-model", "env-model", "claude-sonnet-4-20250514"]


async def test_generate_subtasks_raises_for_invalid_subtask_count(
    monkeypatch: pytest.MonkeyPatch, backend_profile: BackendProfile
) -> None:
    monkeypatch.setattr(
        "pentest.agents.generator.load_fase_index", lambda scan_path, skills_dir: "idx"
    )
    monkeypatch.setattr(
        "pentest.agents.generator.render_generator_prompt",
        lambda input_text, profile, fase_index, context: ("sys", "usr"),
    )
    monkeypatch.setattr("pentest.agents.generator.ChatAnthropic", lambda **kwargs: object())
    monkeypatch.setattr(
        "pentest.agents.generator.create_agent_graph",
        lambda llm, tools, barrier_names, max_iterations: _FakeGraph(
            {
                "barrier_hit": True,
                "barrier_result": {
                    "subtasks": [
                        {"title": f"Task {idx}", "description": "Desc", "fase": "fase-1"}
                        for idx in range(1, 17)
                    ]
                },
            }
        ),
    )

    with pytest.raises(GeneratorError, match="Generator failed to produce a plan"):
        await generate_subtasks("scan", backend_profile, "/skills")
