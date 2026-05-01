from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from pentest.agents.generator import generate_subtasks
from pentest.models.recon import BackendProfile

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.filterwarnings(
        "ignore:The model 'claude-sonnet-4-20250514' is deprecated:DeprecationWarning"
    ),
]


def _load_anthropic_key_from_dotenv() -> None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dotenv_path = os.path.join(repo_root, ".env")
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key != "ANTHROPIC_API_KEY":
                continue
            os.environ[key] = value.strip().strip('"').strip("'")
            return


@pytest.fixture
def skills_dir(tmp_path: Path) -> str:
    for fase in ("fase-1", "fase-3"):
        skill_dir = tmp_path / f"scan-{fase}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"""---
description: Execute FASE 1 - Test phase for generator. Invoke with /scan-fase-1 {{url}}.
---
# {fase}
""",
            encoding="utf-8",
        )
    return str(tmp_path)


async def test_generate_subtasks_with_real_claude(
    skills_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _load_anthropic_key_from_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is required for real Claude E2E test")

    monkeypatch.delenv("GENERATOR_MODEL", raising=False)

    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3"],
        configs={
            "url": "https://example.supabase.co",
            "anon_key": "public-anon-key-placeholder",
        },
        subdomains=[],
    )

    subtasks = await generate_subtasks("scan https://example.com", profile, skills_dir)

    assert 1 <= len(subtasks) <= 15
    assert all(item.title for item in subtasks)
    assert all(item.description for item in subtasks)
    assert any(item.fase for item in subtasks)
