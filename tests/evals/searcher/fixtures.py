from typing import Any

from langchain_core.tools import StructuredTool, tool


def create_search_fixture_tools(interceptor: Any) -> list[StructuredTool]:
    """Creates a list of structured tools that delegate to the interceptor."""

    @tool
    def duckduckgo(query: str) -> str:
        """Performs a duckduckgo search."""
        return str(interceptor.intercept("duckduckgo", {"query": query}))

    @tool
    def tavily_search(query: str) -> str:
        """Performs a tavily search."""
        return str(interceptor.intercept("tavily_search", {"query": query}))

    @tool
    def search_answer(query: str) -> str:
        """Provides an answer based on search results."""
        return str(interceptor.intercept("search_answer", {"query": query}))

    @tool
    def browser(url: str) -> str:
        """Browses a URL."""
        return str(interceptor.intercept("browser", {"url": url}))

    return [duckduckgo, tavily_search, search_answer, browser]
