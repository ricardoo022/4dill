"""Unit tests for Generator prompt renderer (Layer 1)."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from jinja2.exceptions import TemplateNotFound

from pentest.templates.renderer import render_generator_prompt


class TestGeneratorPromptRenderer:
    """Tests for render_generator_prompt function."""

    @pytest.fixture
    def sample_backend_profile(self) -> dict:
        """Sample FASE 0 backend profile."""
        return {
            "target": "https://example.com",
            "technologies": ["Django", "PostgreSQL", "Redis"],
            "detected_ports": [80, 443, 5432],
            "vulnerabilities": ["CVE-2023-1234"],
        }

    @pytest.fixture
    def sample_fase_index(self) -> str:
        """Sample fase_index from US-042."""
        return """
## Available Phases

### FASE 1: Reconnaissance
- scan-fase-1: Initial port and service scanning

### FASE 2: Enumeration
- enum-fase-2: Database enumeration

### FASE 3: Exploitation
- exploit-fase-3: Attempt known vulnerabilities
        """

    def test_render_with_all_variables_populated(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """Successful rendering with all variables populated."""
        input_text = "scan https://example.com for vulnerabilities"
        execution_context = "Previous scan found port 443 open"

        system_prompt, user_prompt = render_generator_prompt(
            input_text=input_text,
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
            execution_context=execution_context,
        )

        # Verify both prompts are non-empty strings
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)
        assert len(system_prompt) > 0
        assert len(user_prompt) > 0

    def test_render_with_empty_execution_context(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """Rendering with empty execution_context parameter."""
        input_text = "scan https://target.local"

        system_prompt, user_prompt = render_generator_prompt(
            input_text=input_text,
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
            execution_context="",
        )

        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)
        assert "first analysis phase" in user_prompt.lower()

    def test_system_prompt_contains_generator_role(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """System prompt contains Generator agent role definition."""
        system_prompt, _ = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        assert "Generator agent" in system_prompt
        assert "SecureDev PentestAI" in system_prompt

    def test_system_prompt_mentions_available_tools(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """System prompt mentions available tools."""
        system_prompt, _ = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        assert "terminal" in system_prompt
        assert "browser" in system_prompt
        assert "searcher" in system_prompt
        assert "memorist" in system_prompt

    def test_system_prompt_specifies_subtask_requirements(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """System prompt specifies subtask structure requirements."""
        system_prompt, _ = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        # Check for required subtask fields
        assert "title" in system_prompt
        assert "description" in system_prompt
        assert "fase" in system_prompt
        # Check for the 15 subtask limit
        assert "15" in system_prompt

    def test_user_prompt_includes_input_text(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """User prompt includes the provided input text."""
        input_text = "scan https://example.com for vulnerabilities"

        _, user_prompt = render_generator_prompt(
            input_text=input_text,
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        assert input_text in user_prompt

    def test_user_prompt_includes_backend_profile_json(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """User prompt includes backend profile as JSON."""
        _, user_prompt = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        # Extract JSON block from the user prompt and validate its contents
        match = re.search(r"```json\n(.+?)```", user_prompt, re.DOTALL)
        assert match is not None, "Expected a JSON code block in user prompt"

        parsed = json.loads(match.group(1).strip())
        assert parsed == sample_backend_profile

    def test_raises_template_not_found_when_prompts_dir_missing(self) -> None:
        """Ensure TemplateNotFound or OS error is raised when prompts dir is missing."""
        sample_backend_profile = {"target": "https://x"}
        sample_fase_index = ""

        # Patch Path.__truediv__ to return a non-existent path so the loader fails
        with patch("pentest.templates.renderer.Path.__truediv__") as mock_div:
            mock_div.return_value = Path("/nonexistent/path")

            with pytest.raises((TemplateNotFound, OSError)):
                render_generator_prompt(
                    input_text="scan",
                    backend_profile=sample_backend_profile,
                    fase_index=sample_fase_index,
                )

    def test_user_prompt_includes_fase_index(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """User prompt includes the fase_index content."""
        _, user_prompt = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        assert "Available Phases" in user_prompt
        assert "Reconnaissance" in user_prompt

    def test_user_prompt_includes_execution_context_when_provided(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """User prompt includes execution context when provided."""
        context = "Previous findings: Port 443 has weak SSL cipher"

        _, user_prompt = render_generator_prompt(
            input_text="scan target",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
            execution_context=context,
        )

        assert context in user_prompt
        assert "Previous findings" in user_prompt

    def test_render_preserves_backend_profile_structure(
        self,
        sample_fase_index: str,
    ) -> None:
        """Renderer correctly handles complex backend profile dict."""
        complex_profile = {
            "target": "https://api.example.com",
            "technologies": ["FastAPI", "PostgreSQL", "Redis"],
            "endpoints": [
                {"path": "/api/users", "method": "GET", "auth": True},
                {"path": "/api/scan", "method": "POST", "auth": False},
            ],
            "headers": {"Server": "FastAPI", "X-Powered-By": "Python"},
            "status_codes": [200, 401, 404, 500],
        }

        _, user_prompt = render_generator_prompt(
            input_text="scan api",
            backend_profile=complex_profile,
            fase_index=sample_fase_index,
        )

        assert "FastAPI" in user_prompt
        assert "/api/users" in user_prompt or "endpoints" in user_prompt

    def test_render_tuple_order_is_correct(
        self, sample_backend_profile: dict, sample_fase_index: str
    ) -> None:
        """Rendered tuple is (system_prompt, user_prompt) in correct order."""
        result = render_generator_prompt(
            input_text="scan",
            backend_profile=sample_backend_profile,
            fase_index=sample_fase_index,
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        # System prompt should contain role info
        assert "Generator agent" in system or "SecureDev" in system
        # User prompt should contain the goal
        assert "scan" in user
