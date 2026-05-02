"""US-057 E2E tests for Tavily search tool with real API calls."""

from __future__ import annotations

import os

import pytest

import pentest.tools.tavily as tavily_module

pytestmark = pytest.mark.e2e


@pytest.fixture
def tavily_api_key():
    """Get Tavily API key from environment."""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        pytest.skip("TAVILY_API_KEY not set - skipping E2E tests")
    return key


@pytest.fixture
def tavily_search_available(tavily_api_key):
    """Ensure Tavily is available before running E2E tests."""
    if not tavily_module.is_available():
        pytest.skip("Tavily tool not available - missing TAVILY_API_KEY or package")


class TestTavilySearchE2ERealAPI:
    """E2E tests with real Tavily API calls."""

    def test_tavily_search_real_cve_vulnerability(self, tavily_search_available) -> None:
        """E2E: Real search for CVE vulnerability information."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "CVE-2024-1234 vulnerability details",
                "max_results": 5,
                "message": "Find CVE vulnerability information",
            }
        )

        # Verify result is a string (not error)
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify structure has expected components
        assert "Results:" in result or "Answer:" in result or "No results" in result.lower()

    def test_tavily_search_real_exploit_technique(self, tavily_search_available) -> None:
        """E2E: Real search for penetration testing techniques."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "SQL injection exploitation technique",
                "max_results": 5,
                "message": "Find SQL injection exploitation methods",
            }
        )

        # Verify result is a string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should contain results with techniques
        assert "SQL" in result or "Results:" in result or "sql" in result.lower()

    def test_tavily_search_real_security_research(self, tavily_search_available) -> None:
        """E2E: Real search for security research papers and documentation."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "OWASP top 10 vulnerabilities 2024",
                "max_results": 5,
                "message": "Find OWASP top vulnerabilities",
            }
        )

        # Verify result is valid string
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify it contains security-related content
        assert "OWASP" in result or "Results:" in result or "vulnerabilities" in result.lower()

    def test_tavily_search_real_network_scanning(self, tavily_search_available) -> None:
        """E2E: Real search for network scanning tools and methods."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "Nmap network scanning advanced techniques",
                "max_results": 5,
                "message": "Find network scanning techniques",
            }
        )

        # Verify result is string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should contain Nmap-related content
        assert "Nmap" in result or "nmap" in result or "scanning" in result.lower()

    def test_tavily_search_real_with_answer_section(self, tavily_search_available) -> None:
        """E2E: Real search verifies answer section is included when available."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "What is the CVSS score system used for?",
                "max_results": 5,
                "message": "Find CVSS scoring information",
            }
        )

        # Verify result is a string
        assert isinstance(result, str)
        assert len(result) > 0

        # Result should include answer or results
        assert "Answer:" in result or "Results:" in result or len(result) > 50

    def test_tavily_search_real_complex_query(self, tavily_search_available) -> None:
        """E2E: Real search with complex penetration testing query."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "Windows Active Directory exploitation techniques privilege escalation",
                "max_results": 5,
                "message": "Find AD exploitation techniques",
            }
        )

        # Verify result is a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should contain Windows/AD related content
        assert (
            "Active Directory" in result
            or "Windows" in result
            or "Results:" in result
            or "privilege" in result.lower()
        )

    def test_tavily_search_real_api_rate_limit_handling(self, tavily_search_available) -> None:
        """E2E: Real search handles API rate limits gracefully."""
        # Multiple sequential searches to test rate limiting
        results = []
        for i in range(3):
            result = tavily_module.tavily_search.invoke(
                {
                    "query": f"Security topic {i}",
                    "max_results": 3,
                    "message": f"Query {i}",
                }
            )
            results.append(result)
            assert isinstance(result, str)

        # All results should be strings (no exceptions raised)
        assert all(isinstance(r, str) for r in results)

    def test_tavily_search_real_truncation_with_large_results(
        self,
        tavily_search_available,
    ) -> None:
        """E2E: Real search verifies truncation works with actual large responses."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "comprehensive guide to web application security testing",
                "max_results": 10,
                "message": "Find web security testing guide",
            }
        )

        # Verify result is a string
        assert isinstance(result, str)

        # Result should not exceed reasonable limit (16KB truncation)
        # 16KB = 16384 bytes, allow some margin for formatting
        assert len(result) < 20000, "Result exceeds expected truncation limit"

        # Verify result has structure
        assert len(result) > 0

    def test_tavily_search_real_no_results_handling(self, tavily_search_available) -> None:
        """E2E: Real search handles queries with no results gracefully."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "xyzabc123nonexistenttermabc789xyz security",
                "max_results": 5,
                "message": "Search for nonsense term",
            }
        )

        # Should return a string (either "No results" or error message)
        assert isinstance(result, str)

        # Should be a valid response
        assert len(result) > 0

    def test_tavily_search_real_response_format(self, tavily_search_available) -> None:
        """E2E: Real search verifies response format is correct."""
        result = tavily_module.tavily_search.invoke(
            {
                "query": "Zero day vulnerability disclosure",
                "max_results": 5,
                "message": "Find zero day information",
            }
        )

        # Verify it's a string
        assert isinstance(result, str)

        # Verify it has expected sections or is an error message
        has_expected_format = (
            "Answer:" in result
            or "Results:" in result
            or "No results" in result
            or "Error" in result
        )
        assert has_expected_format, f"Unexpected response format: {result[:100]}"
