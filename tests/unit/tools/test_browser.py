import asyncio

import httpx
import pytest
import respx
from pydantic import ValidationError

from pentest.models.tool_args import BrowserAction
from pentest.tools.browser import create_browser_tool, create_mock_browser_tool


def test_browser_action_validation():
    """Test that BrowserAction validates correctly."""
    # Missing required fields
    with pytest.raises(ValidationError):
        BrowserAction(url="http://example.com")

    # Valid minimal
    ba = BrowserAction(url="http://example.com", message="test")
    assert ba.url == "http://example.com"
    assert ba.action == "markdown"

    # Valid with custom action
    ba2 = BrowserAction(url="http://example.com", action="links", message="test")
    assert ba2.action == "links"

    # Invalid action should fail
    with pytest.raises(ValidationError):
        BrowserAction(url="http://example.com", action="invalid", message="test")


@pytest.mark.asyncio
async def test_browser_tool_markdown_extraction():
    """Test markdown extraction from HTML content."""
    tool = create_browser_tool()
    html_content = """
    <html><body>
        <h1>Page Title</h1>
        <p>This is a paragraph.</p>
        <a href="http://example.com">Link</a>
    </body></html>
    """

    with respx.mock:
        respx.get("http://example.com").mock(return_value=httpx.Response(200, text=html_content))
        result = await tool.arun(
            {"url": "http://example.com", "action": "markdown", "message": "test"}
        )
        assert isinstance(result, str)
        assert "Title" in result or "paragraph" in result or "Link" in result


@pytest.mark.asyncio
async def test_browser_tool_links_extraction():
    """Test link extraction from HTML content."""
    tool = create_browser_tool()
    html_content = """
    <html><body>
        <a href="http://example.com">Example</a>
        <a href="http://test.com">Test</a>
        <a href="/relative">Relative</a>
    </body></html>
    """

    with respx.mock:
        respx.get("http://example.com/page").mock(
            return_value=httpx.Response(200, text=html_content)
        )
        result = await tool.arun(
            {"url": "http://example.com/page", "action": "links", "message": "test"}
        )
        assert "http://example.com" in result
        assert "http://test.com" in result


@pytest.mark.asyncio
async def test_browser_tool_html_action():
    """Test raw HTML extraction."""
    tool = create_browser_tool()
    html_content = "<html><body><p>Test content</p></body></html>"

    with respx.mock:
        respx.get("http://example.com").mock(return_value=httpx.Response(200, text=html_content))
        result = await tool.arun({"url": "http://example.com", "action": "html", "message": "test"})
        assert "<body>" in result or "Test content" in result


@pytest.mark.asyncio
async def test_browser_tool_truncation():
    """Test that output is truncated to 16KB."""
    tool = create_browser_tool()
    # Create large HTML content
    large_content = f"<html><body>{'x' * 20000}</body></html>"

    with respx.mock:
        respx.get("http://example.com").mock(return_value=httpx.Response(200, text=large_content))
        result = await tool.arun({"url": "http://example.com", "action": "html", "message": "test"})
        # Max should be around 16000 chars + newline + "[truncated]" (total ~16020)
        assert len(result) <= 16030
        assert "...[truncated]" in result


@pytest.mark.asyncio
async def test_browser_tool_error_handling():
    """Test error handling for network errors."""
    tool = create_browser_tool()

    with respx.mock:
        respx.get("http://example.com").mock(side_effect=httpx.ConnectError("Connection failed"))
        result = await tool.arun(
            {"url": "http://example.com", "action": "markdown", "message": "test"}
        )
        assert isinstance(result, str)
        assert "browser tool error" in result


@pytest.mark.asyncio
async def test_browser_tool_timeout():
    """Test timeout handling with actual timeout exception."""
    tool = create_browser_tool()

    with respx.mock:
        respx.get("http://example.com").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        result = await tool.arun(
            {"url": "http://example.com", "action": "markdown", "message": "test"}
        )
        assert isinstance(result, str)
        assert "request timeout after 30 seconds" in result


def test_mock_browser_tool():
    """Test that mock browser tool executes without network."""
    tool = create_mock_browser_tool()
    # Mock tools are async, so we run them in an event loop
    result = asyncio.run(
        tool.arun({"url": "http://example.com", "action": "markdown", "message": "test"})
    )
    assert "Mock markdown content" in result


def test_mock_browser_tool_links():
    """Test mock browser tool with links action."""
    tool = create_mock_browser_tool()
    result = asyncio.run(
        tool.arun({"url": "http://example.com", "action": "links", "message": "test"})
    )
    assert "https://example.com" in result
