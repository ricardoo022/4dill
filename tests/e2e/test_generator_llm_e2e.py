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
]


def _load_provider_key_from_dotenv() -> str:
    """Load provider API key from .env file (supports multiple providers).

    Returns:
        The provider name that has a valid API key loaded.
    """
    from pentest.config import get_default_provider

    # Check providers in order:
    # 1) explicit GENERATOR_PROVIDER / LLM_PROVIDER
    # 2) key-driven preference (OPENAI first, then Anthropic)
    # 3) default provider and remaining known providers.
    providers_to_try: list[str] = []
    if os.getenv("GENERATOR_PROVIDER"):
        providers_to_try.append(os.getenv("GENERATOR_PROVIDER").lower())
    if os.getenv("LLM_PROVIDER"):
        llm_provider = os.getenv("LLM_PROVIDER").lower()
        if llm_provider not in providers_to_try:
            providers_to_try.append(llm_provider)

    if os.getenv("OPENAI_API_KEY") and "openai" not in providers_to_try:
        providers_to_try.append("openai")
    if os.getenv("ANTHROPIC_API_KEY") and "anthropic" not in providers_to_try:
        providers_to_try.append("anthropic")

    default_provider = get_default_provider()
    if default_provider not in providers_to_try:
        providers_to_try.append(default_provider)

    for fallback_provider in ("anthropic", "openai"):
        if fallback_provider not in providers_to_try:
            providers_to_try.append(fallback_provider)

    for provider in providers_to_try:
        key_env_var = f"{provider.upper()}_API_KEY"
        if os.getenv(key_env_var):
            os.environ["GENERATOR_PROVIDER"] = provider
            return provider

    # Try loading from .env file
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dotenv_path = os.path.join(repo_root, ".env")
    if not os.path.exists(dotenv_path):
        return providers_to_try[-1]

    env_vars = {}
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
            env_vars[key.strip()] = value.strip().strip('"').strip("'")

    for provider in providers_to_try:
        key_env_var = f"{provider.upper()}_API_KEY"
        if key_env_var in env_vars:
            os.environ[key_env_var] = env_vars[key_env_var]
            os.environ["GENERATOR_PROVIDER"] = provider
            return provider

    return providers_to_try[-1]


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


async def test_generate_subtasks_with_real_llm(
    skills_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2E test with real LLM (provider-agnostic via config/env).

    The provider and model are resolved via:
    1. Explicit parameters to generate_subtasks() (provider=, model=)
    2. GENERATOR_PROVIDER / GENERATOR_MODEL env vars (agent-specific)
    3. LLM_PROVIDER / LLM_MODEL env vars (generic)
    4. Default provider from pentest.config (temporary: Anthropic)

    To run with Anthropic: set ANTHROPIC_API_KEY in .env
    To run with OpenAI: set GENERATOR_PROVIDER=openai and OPENAI_API_KEY in .env
    To run with local model: set GENERATOR_PROVIDER=ollama (future support)
    """
    provider = _load_provider_key_from_dotenv()
    key_env_var = f"{provider.upper()}_API_KEY"

    if not os.getenv(key_env_var):
        pytest.skip(
            f"{key_env_var} is required for real LLM E2E test. "
            f"Configure provider via GENERATOR_PROVIDER env var (current: {provider}). "
            f"Supported providers: anthropic, openai"
        )

    # Clear explicit model override so provider resolution still follows env/config.
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
