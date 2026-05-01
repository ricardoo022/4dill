import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from pentest.models.tool_args import SploitusAction
from pentest.tools.sploitus import sploitus


def test_sploitus_action_validation():
    """Test validation of SploitusAction model."""
    # Valid
    action = SploitusAction(query="CVE-2021-44228", message="Searching for Log4Shell")
    assert action.query == "CVE-2021-44228"
    assert action.max_results == 10

    # Invalid: empty query
    with pytest.raises(ValidationError):
        SploitusAction(query="", message="Test")

    # Invalid: max_results out of range
    with pytest.raises(ValidationError):
        SploitusAction(query="test", max_results=0, message="Test")
    with pytest.raises(ValidationError):
        SploitusAction(query="test", max_results=26, message="Test")


@respx.mock
@pytest.mark.asyncio
async def test_sploitus_tool_success():
    """Test successful search in Sploitus."""
    mock_response = {
        "exploits": [
            {
                "title": "Log4Shell Exploit",
                "href": "https://sploitus.com/exploit?id=1",
                "score": 9.8,
                "published": "2021-12-10",
                "source": "Github",
            }
        ]
    }
    respx.post("https://sploitus.com/search").return_value = Response(200, json=mock_response)

    result = await sploitus.arun(
        {"query": "log4shell", "max_results": 5, "message": "Searching exploits"}
    )

    assert "# Sploitus Search Results for: log4shell" in result
    assert "Log4Shell Exploit" in result
    assert "https://sploitus.com/exploit?id=1" in result
    assert "Score: 9.8" in result


@respx.mock
@pytest.mark.asyncio
async def test_sploitus_tool_no_results():
    """Test search with no results."""
    respx.post("https://sploitus.com/search").return_value = Response(200, json={"exploits": []})

    result = await sploitus.arun({"query": "nonexistent_query", "message": "Searching"})

    assert "No Sploitus results found for query: nonexistent_query" in result


@respx.mock
@pytest.mark.asyncio
async def test_sploitus_tool_rate_limit():
    """Test rate limit handling (HTTP 422/499)."""
    respx.post("https://sploitus.com/search").return_value = Response(422)

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus: rate limit or validation error (HTTP 422)" in result


@respx.mock
@pytest.mark.asyncio
async def test_sploitus_tool_http_error():
    """Test general HTTP error handling."""
    respx.post("https://sploitus.com/search").return_value = Response(500)

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus:" in result
    assert "500" in result


@respx.mock
@pytest.mark.asyncio
async def test_sploitus_tool_truncation():
    """Test output truncation."""
    long_source = "A" * 1000
    mock_response = {
        "exploits": [
            {
                "title": f"Exploit {i}",
                "href": f"https://sploitus.com/exploit?id={i}",
                "published": "2024-01-01",
                "source": long_source,
            }
            for i in range(25)
        ]
    }
    # Adjust mock to return many results to trigger overall truncation if possible
    # But here let's just check if source snippet is truncated
    respx.post("https://sploitus.com/search").return_value = Response(200, json=mock_response)

    result = await sploitus.arun({"query": "test", "max_results": 25, "message": "Searching"})

    # Check source snippet truncation (per result)
    assert "Source Snippet:" in result
    # We use ... for snippet truncation
    assert "..." in result

    # Check overall truncation (16KB)
    # If the output exceeds 16KB, it should have the [truncated] marker
    if len(result) > 16000:
        assert "...[truncated]" in result
