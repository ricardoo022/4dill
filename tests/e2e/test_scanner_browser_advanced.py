import os
from pathlib import Path

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from pentest.agents.base import create_agent_graph
from pentest.tools.barriers import hack_result
from pentest.tools.browser import create_browser_tool

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _get_llm():
    """Get an LLM for the E2E test based on available environment variables."""
    # First try loading from .env if running locally
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dotenv_path = os.path.join(repo_root, ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path, encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    if line.startswith("export "):
                        line = line.removeprefix("export ").strip()
                    key, value = line.split("=", 1)
                    if key.strip() in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")

    if os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(model="gpt-4o", temperature=0)
    elif os.getenv("ANTHROPIC_API_KEY"):
        return ChatAnthropic(model="claude-3-5-sonnet-latest", temperature=0)
    else:
        pytest.skip("No API key available for LLM. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")


async def test_scanner_browser_advanced_mode(tmp_path: Path):
    """Test that a scanner agent graph can use the browser in advanced mode.

    It should fetch a local file that relies on JavaScript rendering, read
    the content successfully, and return it via the hack_result barrier.
    """
    llm = _get_llm()
    browser_tool = create_browser_tool()

    graph = create_agent_graph(
        llm=llm,
        tools=[browser_tool, hack_result],
        barrier_names=["hack_result"],
        max_iterations=10,
    )

    prompt = """
    You are a scanner testing this URL: https://example.com

    You must use the `browser` tool in `advanced` mode with `action='screenshot'` to capture the visual state of the page.
    Once the screenshot is successfully taken, call `hack_result` with the path to the screenshot in the `result` field.
    """

    result = await graph.ainvoke({"messages": [HumanMessage(content=prompt)]})

    # Verify the agent successfully hit the barrier
    assert result.get("barrier_hit") is True, "Agent did not hit the hack_result barrier"
    barrier_args = result.get("barrier_result")
    assert barrier_args is not None, "No arguments provided to hack_result"

    # Verify the agent successfully took a screenshot
    result_text = barrier_args.get("result", "")
    assert "screenshot" in result_text.lower() or "png" in result_text.lower(), f"Agent failed to report screenshot: {result_text}"
