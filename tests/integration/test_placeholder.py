"""Placeholder to ensure pytest discovers this directory."""

import pytest


@pytest.mark.integration
def test_integration_directory_exists() -> None:
    """Verify integration test infrastructure is in place."""
