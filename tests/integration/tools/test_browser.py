from pathlib import Path

import pytest

from pentest.tools.browser import create_browser_tool


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browser_advanced_mode_rendering():
    """Test that advanced mode renders JavaScript content.

    We use a data URI with JS to simulate a simple SPA.
    """
    tool = create_browser_tool()

    # Simple HTML that uses JS to inject text
    js_html = """
    <html>
        <body>
            <div id="content">Loading...</div>
            <script>
                setTimeout(() => {
                    document.getElementById('content').innerText = 'JS Rendered Content';
                }, 100);
            </script>
        </body>
    </html>
    """
    # Create a temporary file to load via file://
    temp_file = Path("/tmp/test_spa.html")
    temp_file.write_text(js_html)

    url = f"file://{temp_file.absolute()}"

    try:
        advanced_result = await tool.arun(
            {"url": url, "mode": "advanced", "action": "markdown", "message": "test advanced"}
        )

        assert "JS Rendered Content" in advanced_result
        assert "Loading..." not in advanced_result
    finally:
        if temp_file.exists():
            temp_file.unlink()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browser_screenshot_generation():
    """Test that advanced mode generates a screenshot file."""
    tool = create_browser_tool()
    url = "https://example.com"

    result = await tool.arun(
        {"url": url, "mode": "advanced", "action": "screenshot", "message": "take screenshot"}
    )

    assert "Screenshot saved to:" in result
    path_str = result.split("Screenshot saved to: ")[1].strip()
    path = Path(path_str)

    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 0

    # Cleanup
    if path.exists():
        path.unlink()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browser_advanced_mode_timeout():
    """Test timeout handling in advanced mode."""
    tool = create_browser_tool()
    # Use a non-existent URL or one that hangs if possible
    url = "http://10.255.255.1"  # Non-routable IP

    result = await tool.arun(
        {
            "url": url,
            "mode": "advanced",
            "action": "markdown",
            "message": "test timeout",
            "timeout": 1,  # This timeout is for the tool, not playwright internal
        }
    )

    assert "browser tool error (advanced mode)" in result or "timeout" in result.lower()
