"""Placeholder to ensure pytest discovers this directory."""

import pytest


@pytest.mark.agent
def test_agent_directory_exists() -> None:
    """Verify agent test infrastructure is in place."""
