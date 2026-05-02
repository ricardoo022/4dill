import json
import os
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from pentest.models.tool_args import SploitusAction
from pentest.tools.sploitus import sploitus


def test_sploitus_action_clamping():
    """Test clamping of max_results in SploitusAction model."""
    # Too low: should clamp to 10
    action = SploitusAction(query="test", max_results=0, message="Test")
    assert action.max_results == 10

    # Too high: should clamp to 25
    action = SploitusAction(query="test", max_results=100, message="Test")
    assert action.max_results == 25

    # Valid: should stay same
    action = SploitusAction(query="test", max_results=15, message="Test")
    assert action.max_results == 15

    # Invalid type: should fallback to 10
    action = SploitusAction(query="test", max_results="invalid", message="Test")
    assert action.max_results == 10


def test_sploitus_action_validation():
    """Test basic validation of SploitusAction model."""
    # Valid
    action = SploitusAction(query="CVE-2021-44228", message="Searching for Log4Shell")
    assert action.query == "CVE-2021-44228"

    # Invalid: empty query
    with pytest.raises(ValidationError):
        SploitusAction(query="", message="Test")


@respx.mock
async def test_sploitus_tool_success_exploits():
    """Test successful exploits search in Sploitus with full formatting check."""
    mock_response = {
        "exploits": [
            {
                "title": "Log4Shell Exploit",
                "href": "https://sploitus.com/exploit?id=1",
                "score": 9.8,
                "published": "2021-12-10",
                "source": "Github",
                "language": "Java",
            }
        ]
    }

    # Strict request matching
    route = respx.post("https://sploitus.com/search")
    route.return_value = Response(200, json=mock_response)

    result = await sploitus.arun(
        {"query": "log4shell", "max_results": 5, "message": "Searching exploits"}
    )

    # Verify Request
    assert route.called
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Origin"] == "https://sploitus.com"
    assert "log4shell" in request.headers["Referer"]

    payload = json.loads(request.content)
    assert payload["query"] == "log4shell"
    assert payload["type"] == "exploits"
    assert payload["sort"] == "default"

    # Verify Response Formatting
    assert "# Sploitus Search Results for: log4shell" in result
    assert "Type: exploits" in result
    assert "Total matches: 1" in result
    assert "Log4Shell Exploit" in result
    assert "URL: https://sploitus.com/exploit?id=1" in result
    assert "Language: Java" in result
    assert "Score: 9.8" in result


@respx.mock
async def test_sploitus_tool_success_tools():
    """Test successful tools search in Sploitus."""
    mock_response = {
        "tools": [
            {
                "title": "Nmap",
                "href": "https://nmap.org",
                "published": "2024-01-01",
                "source": "Official",
            }
        ]
    }
    respx.post("https://sploitus.com/search").return_value = Response(200, json=mock_response)

    result = await sploitus.arun(
        {"query": "nmap", "exploit_type": "tools", "message": "Searching tools"}
    )

    assert "Type: tools" in result
    assert "Download URL: https://nmap.org" in result


@respx.mock
async def test_sploitus_tool_no_results():
    """Test search with no results."""
    respx.post("https://sploitus.com/search").return_value = Response(200, json={"exploits": []})

    result = await sploitus.arun({"query": "nonexistent_query", "message": "Searching"})

    assert "No Sploitus results found for query: nonexistent_query" in result


@respx.mock
async def test_sploitus_tool_rate_limit_499():
    """Test rate limit handling (HTTP 499)."""
    respx.post("https://sploitus.com/search").return_value = Response(499)

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus: rate limit or validation error (HTTP 499)" in result


@respx.mock
async def test_sploitus_tool_rate_limit_422():
    """Test rate limit handling (HTTP 422)."""
    respx.post("https://sploitus.com/search").return_value = Response(422)

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus: rate limit or validation error (HTTP 422)" in result


@respx.mock
async def test_sploitus_tool_invalid_json():
    """Test handling of invalid JSON response."""
    respx.post("https://sploitus.com/search").return_value = Response(200, content="invalid json")

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus: invalid JSON response from server" in result


@respx.mock
async def test_sploitus_tool_disabled():
    """Test tool when disabled via env var."""
    with patch.dict(os.environ, {"SPLOITUS_ENABLED": "false"}):
        result = await sploitus.arun({"query": "test", "message": "Searching"})
        assert "Sploitus tool is currently disabled" in result


@respx.mock
async def test_sploitus_tool_http_error():
    """Test general HTTP error handling."""
    respx.post("https://sploitus.com/search").return_value = Response(500)

    result = await sploitus.arun({"query": "test", "message": "Searching"})

    assert "failed to search in Sploitus:" in result
    assert "500" in result


@respx.mock
async def test_sploitus_tool_truncation():
    """Test output truncation."""
    mock_response = {
        "exploits": [
            {
                "title": f"Exploit {i}",
                "href": f"https://sploitus.com/exploit?id={i}",
                "published": "2024-01-01",
                "source": "A" * 1000,
            }
            for i in range(25)
        ]
    }
    respx.post("https://sploitus.com/search").return_value = Response(200, json=mock_response)

    result = await sploitus.arun({"query": "test", "max_results": 25, "message": "Searching"})

    # Check source snippet truncation (per result)
    assert "Source Snippet:" in result
    assert "..." in result

    # Check overall truncation (16KB)
    if len(result) > 16000:
        assert "...[truncated]" in result
