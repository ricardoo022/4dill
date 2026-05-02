"""US-057 tests for Tavily search tool handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pentest.tools.tavily as tavily_module


def _setup_tavily_client(monkeypatch, search_return=None, search_side_effect=None):
    """Set up mocked TavilyClient for testing."""
    client_instance = MagicMock()
    if search_side_effect is not None:
        client_instance.search.side_effect = search_side_effect
    else:
        client_instance.search.return_value = search_return

    client_class = MagicMock(return_value=client_instance)
    monkeypatch.setattr(tavily_module, "TavilyClient", client_class)
    return client_class, client_instance


class TestIsAvailable:
    """Tests for is_available() function."""

    def test_is_available_returns_true_when_tavily_api_key_set(self, monkeypatch) -> None:
        """is_available() returns True when TAVILY_API_KEY env var is set."""
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")
        monkeypatch.setattr(tavily_module, "TavilyClient", MagicMock())

        assert tavily_module.is_available() is True

    def test_is_available_returns_false_when_tavily_api_key_not_set(self, monkeypatch) -> None:
        """is_available() returns False when TAVILY_API_KEY is not configured."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setattr(tavily_module, "TavilyClient", MagicMock())

        assert tavily_module.is_available() is False

    def test_is_available_returns_false_when_tavily_client_unavailable(self, monkeypatch) -> None:
        """is_available() returns False when tavily-python package not installed."""
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")
        monkeypatch.setattr(tavily_module, "TavilyClient", None)

        assert tavily_module.is_available() is False


class TestTavilySearchBasicFunctionality:
    """Tests for core tavily_search functionality."""

    def test_tavily_search_formats_results_with_scores(self, monkeypatch) -> None:
        """tavily_search formats results with title, url, score, and content."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "CVE-2023-1234 Details",
                        "url": "https://nvd.nist.gov/vuln/detail/CVE-2023-1234",
                        "content": "A vulnerability in OpenSSH...",
                        "score": 0.95,
                    },
                    {
                        "title": "Exploit Proof of Concept",
                        "url": "https://exploit-db.com/exploits/12345",
                        "content": "PoC code for CVE-2023-1234...",
                        "score": 0.87,
                    },
                ],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "CVE-2023-1234", "max_results": 5, "message": "Find CVE info"}
        )

        client_instance.search.assert_called_once_with(
            query="CVE-2023-1234",
            max_results=5,
            search_depth="basic",
            include_answer=True,
        )
        assert "CVE-2023-1234 Details" in result
        assert "score: 0.95" in result
        assert "https://nvd.nist.gov/vuln/detail/CVE-2023-1234" in result
        assert "Exploit Proof of Concept" in result
        assert "score: 0.87" in result

    def test_tavily_search_includes_answer_section_when_available(self, monkeypatch) -> None:
        """tavily_search includes answer section when API returns one."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com/1",
                        "content": "Content 1",
                        "score": 0.9,
                    }
                ],
                "answer": "OpenSSH versions prior to 7.4 are vulnerable to...",
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "OpenSSH vulnerability", "max_results": 5, "message": "Search"}
        )

        assert "Answer: OpenSSH versions prior to 7.4 are vulnerable to..." in result
        assert "Sources:" in result

    def test_tavily_search_excludes_answer_section_when_not_available(self, monkeypatch) -> None:
        """tavily_search excludes Answer section when API doesn't return one."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com/1",
                        "content": "Content 1",
                        "score": 0.9,
                    }
                ],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "query", "max_results": 5, "message": "Search"}
        )

        assert "Sources:" in result
        assert result.count("Answer:") == 0

    def test_tavily_search_no_results(self, monkeypatch) -> None:
        """tavily_search returns no results message when API returns empty list."""
        _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "nonexistent-query-xyz", "max_results": 5, "message": "Search"}
        )

        assert result == "No results found for: nonexistent-query-xyz"

    def test_tavily_search_returns_error_string_on_api_error(self, monkeypatch) -> None:
        """tavily_search returns error string when API call fails."""
        _setup_tavily_client(
            monkeypatch,
            search_side_effect=RuntimeError("API rate limit exceeded"),
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "query", "max_results": 5, "message": "Search"}
        )

        assert result == "tavily search error: API rate limit exceeded"


class TestTavilySearchParameterHandling:
    """Tests for parameter handling and validation."""

    def test_tavily_search_max_results_passthrough(self, monkeypatch) -> None:
        """tavily_search passes max_results parameter to Tavily API."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={"results": [], "answer": None},
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        tavily_module.tavily_search.invoke(
            {"query": "test query", "max_results": 3, "message": "Search"}
        )

        client_instance.search.assert_called_once_with(
            query="test query",
            max_results=3,
            search_depth="basic",
            include_answer=True,
        )

    def test_tavily_search_uses_basic_search_depth(self, monkeypatch) -> None:
        """tavily_search uses search_depth='basic' by default."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={"results": [], "answer": None},
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        tavily_module.tavily_search.invoke({"query": "test", "max_results": 5, "message": "Search"})

        client_instance.search.assert_called_once()
        call_kwargs = client_instance.search.call_args[1]
        assert call_kwargs["search_depth"] == "basic"
        assert call_kwargs["include_answer"] is True

    def test_tavily_search_include_answer_always_true(self, monkeypatch) -> None:
        """tavily_search always includes include_answer=True in API call."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={"results": [], "answer": None},
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        tavily_module.tavily_search.invoke({"query": "test", "max_results": 5, "message": "Search"})

        call_kwargs = client_instance.search.call_args[1]
        assert call_kwargs["include_answer"] is True


class TestTavilySearchOutputFormatting:
    """Tests for output formatting and truncation."""

    def test_tavily_search_truncates_content_to_2kb_per_result(self, monkeypatch) -> None:
        """tavily_search truncates each result's content to 2KB."""
        long_content = "x" * 3000
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "Long content result",
                        "url": "https://example.com/long",
                        "content": long_content,
                        "score": 0.9,
                    }
                ],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        # Content should be truncated to 2KB + truncation marker
        assert len(long_content) >= 3000
        assert "...[truncated]" in result
        # The result should not contain the full 3000-char content
        assert result.count("x") < 3000

    def test_tavily_search_truncates_overall_output_to_16kb(self, monkeypatch) -> None:
        """tavily_search truncates overall output to 16KB max."""
        # Create multiple results with long content to exceed 16KB
        results = []
        for i in range(10):
            results.append(
                {
                    "title": f"Result {i}",
                    "url": f"https://example.com/{i}",
                    "content": "y" * 2048,  # Each at 2KB max
                    "score": 0.9 - (i * 0.01),
                }
            )

        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={"results": results, "answer": None},
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 10, "message": "Search"}
        )

        assert len(result) <= 16030  # MAX_OUTPUT_LENGTH + truncation marker
        if len(result) == 16030:
            assert result.endswith("...[truncated]")

    def test_tavily_search_formats_scores_to_two_decimals(self, monkeypatch) -> None:
        """tavily_search formats score values to two decimal places."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "Result",
                        "url": "https://example.com",
                        "content": "Content",
                        "score": 0.954321,  # Many decimal places
                    }
                ],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        assert "score: 0.95" in result
        assert "score: 0.954321" not in result

    def test_tavily_search_handles_missing_optional_fields(self, monkeypatch) -> None:
        """tavily_search gracefully handles results with missing optional fields."""
        client_class, client_instance = _setup_tavily_client(
            monkeypatch,
            search_return={
                "results": [
                    {
                        "title": "Minimal result",
                        "url": "https://example.com",
                        # Missing content and score
                    }
                ],
                "answer": None,
            },
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-12345")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        assert "Minimal result" in result
        assert "https://example.com" in result
        # Should have a default score of 0.00
        assert "score: 0.00" in result


class TestTavilySearchErrorHandling:
    """Tests for error handling and edge cases."""

    def test_tavily_search_returns_package_missing_error_when_unavailable(
        self, monkeypatch
    ) -> None:
        """tavily_search returns error when tavily-python not installed."""
        monkeypatch.setattr(tavily_module, "TavilyClient", None)
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        assert result == "tavily search error: tavily-python package not installed"

    def test_tavily_search_returns_error_when_api_key_not_configured(self, monkeypatch) -> None:
        """tavily_search returns error when TAVILY_API_KEY not set."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setattr(tavily_module, "TavilyClient", MagicMock())

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        assert result == "tavily search error: TAVILY_API_KEY environment variable not configured"

    def test_tavily_search_returns_error_on_authentication_failure(self, monkeypatch) -> None:
        """tavily_search returns error string on API authentication failure."""
        _setup_tavily_client(
            monkeypatch,
            search_side_effect=ValueError("Invalid API key"),
        )
        monkeypatch.setenv("TAVILY_API_KEY", "invalid-key")

        result = tavily_module.tavily_search.invoke(
            {"query": "test", "max_results": 5, "message": "Search"}
        )

        assert result == "tavily search error: Invalid API key"

    def test_tavily_search_returns_error_on_timeout(self, monkeypatch) -> None:
        """tavily_search returns error string on timeout."""
        _setup_tavily_client(
            monkeypatch,
            search_side_effect=TimeoutError("Request timed out after 30s"),
        )
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")

        result = tavily_module.tavily_search.invoke(
            {"query": "slow query", "max_results": 5, "message": "Search"}
        )

        assert "tavily search error: Request timed out after 30s" in result


class TestTavilySearchSchema:
    """Tests for LangChain tool schema compatibility."""

    def test_tavily_search_tool_schema_is_function_calling_compatible(self) -> None:
        """tavily_search tool schema is compatible with LLM function calling."""
        schema = tavily_module.tavily_search.args_schema.model_json_schema()
        assert "query" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert "message" in schema["properties"]
        assert "query" in schema["required"]
        assert "message" in schema["required"]

    def test_tavily_search_tool_schema_has_correct_constraints(self) -> None:
        """tavily_search tool schema enforces SearchAction constraints."""
        schema = tavily_module.tavily_search.args_schema.model_json_schema()
        # max_results should have min 1 and max 10
        assert schema["properties"]["max_results"]["minimum"] == 1
        assert schema["properties"]["max_results"]["maximum"] == 10
