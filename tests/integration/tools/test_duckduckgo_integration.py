"""US-056 integration tests for DuckDuckGo search tool."""

import pytest

from pentest.tools.duckduckgo import duckduckgo


@pytest.mark.integration
def test_duckduckgo_real_engine_round_trip() -> None:
    """🔁 Real DDG query returns retrievable formatted output."""
    query = "CVE-2023-38408 OpenSSH advisory"
    result = duckduckgo.invoke(
        {
            "query": query,
            "max_results": 2,
            "message": "Validate real DuckDuckGo integration",
        }
    )

    assert isinstance(result, str)
    assert result.strip()
    assert not result.startswith("duckduckgo search error:")
    if result.startswith("No results found for:"):
        assert query in result
    else:
        assert "1. [" in result
        assert "] - " in result
