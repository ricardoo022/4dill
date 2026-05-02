from __future__ import annotations

import os

import pytest

from pentest.agents.searcher import create_searcher_tool, perform_search
from pentest.providers.factory import create_chat_model
from pentest.tools.duckduckgo import is_available as is_ddg_available
from pentest.tools.tavily import is_available as is_tavily_available

pytestmark = [pytest.mark.e2e]


def _has_provider_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


async def test_perform_search_real_llm_round_trip() -> None:
    if not _has_provider_key():
        pytest.skip("OPENAI_API_KEY or ANTHROPIC_API_KEY is required for e2e searcher test")

    if not is_ddg_available() and not is_tavily_available():
        pytest.skip("No search engine available for e2e searcher test")

    llm = create_chat_model(agent_name="searcher")
    try:
        result = await perform_search(
            question="What is SQL injection? Provide a short answer.",
            llm=llm,
        )
    except Exception as exc:  # pragma: no cover - env-dependent auth/network
        if "authentication_error" in str(exc) or "401" in str(exc):
            pytest.skip("Configured provider API key is invalid for e2e searcher test")
        raise

    assert result
    assert "No search engines available" not in result


async def test_create_searcher_tool_real_llm_round_trip() -> None:
    if not _has_provider_key():
        pytest.skip("OPENAI_API_KEY or ANTHROPIC_API_KEY is required for e2e searcher test")

    if not is_ddg_available() and not is_tavily_available():
        pytest.skip("No search engine available for e2e searcher test")

    llm = create_chat_model(agent_name="searcher")
    search_tool = create_searcher_tool(llm=llm)
    result = await search_tool.ainvoke(
        {
            "question": "List one common web vuln category with one-line explanation.",
            "message": "research",
        }
    )

    if "authentication_error" in result or "Error code: 401" in result:
        pytest.skip("Configured provider API key is invalid for e2e searcher test")

    assert result
    assert "Searcher error:" not in result
