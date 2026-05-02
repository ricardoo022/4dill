"""Unit tests for Searcher prompt templates (Layer 1)."""

import pytest

from pentest.templates.searcher import render_searcher_prompt


class TestSearcherPromptTemplates:
    """Tests for render_searcher_prompt and its templates."""

    @pytest.fixture
    def available_tools(self) -> list[str]:
        """Sample list of available tools."""
        return ["duckduckgo", "browser", "search_answer", "search_result"]

    def test_render_returns_non_empty_prompts(self, available_tools: list[str]) -> None:
        """Verify render_searcher_prompt returns non-empty system and user prompts."""
        system, user = render_searcher_prompt(
            question="What is the latest CVE for Django?",
            available_tools=available_tools,
        )
        assert system.strip() != ""
        assert user.strip() != ""

    def test_system_prompt_contains_search_result_instructions(
        self, available_tools: list[str]
    ) -> None:
        """Verify system prompt contains instructions about search_result tool."""
        system, _ = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
        )
        assert "search_result" in system
        assert "result" in system
        assert "message" in system

    def test_system_prompt_contains_source_priority(self, available_tools: list[str]) -> None:
        """Verify system prompt contains source priority with search_answer first."""
        system, _ = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
        )
        assert "Source Priority" in system

        # Extract the Source Priority section to avoid matches in Available Tools
        priority_section = system.split("Source Priority")[1]

        # Check that search_answer comes before duckduckgo/tavily
        search_answer_pos = priority_section.find("search_answer")
        web_search_pos = priority_section.find("duckduckgo")
        assert search_answer_pos != -1
        assert web_search_pos != -1
        assert search_answer_pos < web_search_pos

    def test_system_prompt_no_store_answer(self, available_tools: list[str]) -> None:
        """Verify system prompt does NOT contain references to store_answer."""
        system, _ = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
        )
        assert "store_answer" not in system

    def test_system_prompt_contains_anonymization_protocol(
        self, available_tools: list[str]
    ) -> None:
        """Verify system prompt contains the anonymization protocol."""
        system, _ = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
        )
        assert "Anonymization Protocol" in system
        assert "{ip}" in system
        assert "{domain}" in system
        assert "{username}" in system

    def test_user_message_contains_question(self, available_tools: list[str]) -> None:
        """Verify user message contains the question."""
        question = "How to exploit SQL injection in PostgreSQL?"
        _, user = render_searcher_prompt(
            question=question,
            available_tools=available_tools,
        )
        assert question in user

    def test_user_message_renders_with_task_and_subtask(self, available_tools: list[str]) -> None:
        """Verify user message renders correctly with task and subtask."""
        task = "Analyze target vulnerabilities"
        subtask = "Search for CVEs"
        _, user = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
            task=task,
            subtask=subtask,
        )
        assert task in user
        assert subtask in user
        assert "Current Task" in user
        assert "Current Subtask" in user

    def test_user_message_renders_with_empty_optional_fields(
        self, available_tools: list[str]
    ) -> None:
        """Verify user message renders without error when optional fields are empty."""
        _, user = render_searcher_prompt(
            question="test",
            available_tools=available_tools,
            task=None,
            subtask=None,
            execution_context="",
        )
        assert "Current Task" not in user
        assert "Current Subtask" not in user
        assert "Execution Context" not in user

    def test_templates_render_with_all_fields(self, available_tools: list[str]) -> None:
        """Verify templates render without error when all fields are provided."""
        question = "What is the capital of France?"
        task = "General knowledge"
        subtask = "Geographic information"
        execution_context = "Scanning the world map"

        system, user = render_searcher_prompt(
            question=question,
            available_tools=available_tools,
            task=task,
            subtask=subtask,
            execution_context=execution_context,
        )

        assert question in user
        assert task in user
        assert subtask in user
        assert execution_context in user
        for tool in available_tools:
            assert tool in system
