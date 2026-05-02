"""US-056 tests for DuckDuckGo search tool handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pentest.tools.duckduckgo as duckduckgo_module


def _setup_ddgs(monkeypatch, text_return=None, text_side_effect=None):
    ddgs_instance = MagicMock()
    if text_side_effect is not None:
        ddgs_instance.text.side_effect = text_side_effect
    else:
        ddgs_instance.text.return_value = text_return

    ddgs_class = MagicMock()
    ddgs_class.return_value.__enter__.return_value = ddgs_instance
    ddgs_class.return_value.__exit__.return_value = False
    monkeypatch.setattr(duckduckgo_module, "DDGS", ddgs_class)
    return ddgs_class, ddgs_instance


def test_duckduckgo_formats_search_results(monkeypatch) -> None:
    _, ddgs_instance = _setup_ddgs(
        monkeypatch,
        text_return=[
            {
                "title": "NVD CVE-2023-1234",
                "href": "https://nvd.nist.gov/cve",
                "body": "CVE details",
            },
            {
                "title": "Exploit DB reference",
                "href": "https://exploit-db.com/example",
                "body": "PoC and references",
            },
        ],
    )

    result = duckduckgo_module.duckduckgo.invoke(
        {"query": "CVE-2023-1234", "max_results": 5, "message": "Find advisories"}
    )

    ddgs_instance.text.assert_called_once_with(
        "CVE-2023-1234",
        region="wt-wt",
        safesearch="moderate",
        max_results=5,
    )
    assert "1. [NVD CVE-2023-1234] - https://nvd.nist.gov/cve" in result
    assert "CVE details" in result
    assert "2. [Exploit DB reference] - https://exploit-db.com/example" in result


def test_duckduckgo_no_results(monkeypatch) -> None:
    _setup_ddgs(monkeypatch, text_return=[])

    result = duckduckgo_module.duckduckgo.invoke(
        {"query": "query-with-no-results", "max_results": 5, "message": "Search"}
    )

    assert result == "No results found for: query-with-no-results"


def test_duckduckgo_returns_error_string_on_engine_exception(monkeypatch) -> None:
    _setup_ddgs(monkeypatch, text_side_effect=RuntimeError("timeout"))

    result = duckduckgo_module.duckduckgo.invoke(
        {"query": "OpenSSH CVE", "max_results": 5, "message": "Search"}
    )

    assert result == "duckduckgo search error: timeout"


def test_duckduckgo_max_results_passthrough(monkeypatch) -> None:
    _, ddgs_instance = _setup_ddgs(monkeypatch, text_return=[])

    duckduckgo_module.duckduckgo.invoke(
        {"query": "OpenSSH CVE", "max_results": 3, "message": "Search"}
    )

    ddgs_instance.text.assert_called_once_with(
        "OpenSSH CVE",
        region="wt-wt",
        safesearch="moderate",
        max_results=3,
    )


def test_duckduckgo_tool_schema_is_function_calling_compatible() -> None:
    schema = duckduckgo_module.duckduckgo.args_schema.model_json_schema()
    assert "query" in schema["properties"]
    assert "max_results" in schema["properties"]
    assert "message" in schema["properties"]
    assert "query" in schema["required"]
    assert "message" in schema["required"]


def test_duckduckgo_output_truncates_at_16kb(monkeypatch) -> None:
    _setup_ddgs(
        monkeypatch,
        text_return=[
            {
                "title": "Very long result",
                "href": "https://example.com/long",
                "body": "x" * 20000,
            }
        ],
    )

    result = duckduckgo_module.duckduckgo.invoke(
        {"query": "long", "max_results": 1, "message": "Search"}
    )

    assert len(result) <= 16030
    assert "...[truncated]" in result


def test_is_available_returns_true_when_engine_reachable(monkeypatch) -> None:
    _setup_ddgs(
        monkeypatch,
        text_return=[{"title": "ok", "href": "https://example.com", "body": "ok"}],
    )

    assert duckduckgo_module.is_available() is True


def test_is_available_returns_false_on_engine_error(monkeypatch) -> None:
    _setup_ddgs(monkeypatch, text_side_effect=RuntimeError("blocked"))

    assert duckduckgo_module.is_available() is False


def test_duckduckgo_uses_30_second_timeout_for_ddgs_client(monkeypatch) -> None:
    ddgs_class, _ = _setup_ddgs(monkeypatch, text_return=[])

    duckduckgo_module.duckduckgo.invoke(
        {"query": "OpenSSH CVE", "max_results": 3, "message": "Search"}
    )

    ddgs_class.assert_called_once_with(timeout=30)


def test_duckduckgo_returns_package_missing_error_when_ddgs_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(duckduckgo_module, "DDGS", None)

    result = duckduckgo_module.duckduckgo.invoke(
        {"query": "OpenSSH CVE", "max_results": 3, "message": "Search"}
    )

    assert result == "duckduckgo search error: duckduckgo-search package not installed"
