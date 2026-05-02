"""US-034: Graphiti environment configuration tests."""

from __future__ import annotations

from pentest.graphiti import GraphitiSettings, get_graphiti_settings


def test_graphiti_settings_default_to_disabled(monkeypatch):
    """Graphiti is opt-in unless explicitly enabled."""
    monkeypatch.delenv("GRAPHITI_ENABLED", raising=False)
    monkeypatch.delenv("GRAPHITI_URL", raising=False)
    monkeypatch.delenv("GRAPHITI_TIMEOUT", raising=False)

    settings = GraphitiSettings.from_env()

    assert settings.enabled is False
    assert settings.is_disabled is True
    assert settings.url == "http://graphiti:8000"
    assert settings.timeout == 30.0


def test_graphiti_settings_read_environment(monkeypatch):
    """Configured env vars are parsed into typed settings."""
    monkeypatch.setenv("GRAPHITI_ENABLED", "true")
    monkeypatch.setenv("GRAPHITI_URL", "http://localhost:8000/")
    monkeypatch.setenv("GRAPHITI_TIMEOUT", "12.5")

    settings = get_graphiti_settings()

    assert settings.enabled is True
    assert settings.is_disabled is False
    assert settings.url == "http://localhost:8000"
    assert settings.timeout == 12.5


def test_graphiti_settings_ignore_invalid_values(monkeypatch):
    """Invalid env vars fall back to safe defaults."""
    monkeypatch.setenv("GRAPHITI_ENABLED", "maybe")
    monkeypatch.setenv("GRAPHITI_TIMEOUT", "slow")

    settings = GraphitiSettings.from_env()

    assert settings.enabled is False
    assert settings.timeout == 30.0
