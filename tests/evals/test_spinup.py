"""Tests for PortSwigger lab spinup (US-046).

Covers:
- AC: auth/credential failures return clear errors without silent crash
- AC: saved session is reused on re-execution
- AC: spinup_lab returns a valid *.web-security-academy.net URL
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.evals.spinup import (
    PortSwiggerAuthError,
    PortSwiggerTimeoutError,
    _load_credentials,
    spinup_lab,
)

LAB_URL = "https://portswigger.net/web-security/sql-injection/lab-login-bypass"
INSTANCE_URL = "https://abc123.web-security-academy.net"


def _make_playwright_mock(instance_url: str = INSTANCE_URL):
    """Build a minimal Playwright mock chain for spinup_lab."""
    mock_lab_page = AsyncMock()
    mock_lab_page.url = instance_url
    mock_lab_page.wait_for_load_state = AsyncMock()
    mock_lab_page.wait_for_url = AsyncMock()

    # Playwright's EventInfo.value is awaitable (a Future); use a coroutine to match.
    async def _lab_page_value():
        return mock_lab_page

    mock_new_page_info = MagicMock()
    mock_new_page_info.value = _lab_page_value()

    mock_expect_page_cm = MagicMock()
    mock_expect_page_cm.__aenter__ = AsyncMock(return_value=mock_new_page_info)
    mock_expect_page_cm.__aexit__ = AsyncMock(return_value=False)

    mock_main_page = AsyncMock()
    mock_main_page.goto = AsyncMock()
    mock_main_page.wait_for_selector = AsyncMock()
    mock_main_page.click = AsyncMock()
    mock_main_page.url = INSTANCE_URL

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_main_page)
    mock_context.expect_page = MagicMock(return_value=mock_expect_page_cm)
    mock_context.add_cookies = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[])

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_playwright_obj = MagicMock()
    mock_playwright_obj.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_cm = MagicMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_playwright_obj)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_pw_cm, mock_context, mock_main_page


class TestCredentialErrors:
    """AC: auth errors are detected clearly without silent crash."""

    def test_missing_both_vars_raises_auth_error(self, monkeypatch):
        monkeypatch.delenv("PORTSWIGGER_EMAIL", raising=False)
        monkeypatch.delenv("PORTSWIGGER_PASSWORD", raising=False)
        with pytest.raises(PortSwiggerAuthError, match="Missing credentials"):
            _load_credentials()

    def test_missing_password_raises_auth_error(self, monkeypatch):
        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.delenv("PORTSWIGGER_PASSWORD", raising=False)
        with pytest.raises(PortSwiggerAuthError, match="Missing credentials"):
            _load_credentials()

    def test_missing_email_raises_auth_error(self, monkeypatch):
        monkeypatch.delenv("PORTSWIGGER_EMAIL", raising=False)
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")
        with pytest.raises(PortSwiggerAuthError, match="Missing credentials"):
            _load_credentials()

    def test_error_message_names_both_env_vars(self, monkeypatch):
        monkeypatch.delenv("PORTSWIGGER_EMAIL", raising=False)
        monkeypatch.delenv("PORTSWIGGER_PASSWORD", raising=False)
        with pytest.raises(PortSwiggerAuthError) as exc_info:
            _load_credentials()
        message = str(exc_info.value)
        assert "PORTSWIGGER_EMAIL" in message
        assert "PORTSWIGGER_PASSWORD" in message

    async def test_spinup_lab_propagates_auth_error(self, monkeypatch):
        """spinup_lab raises PortSwiggerAuthError before touching Playwright."""
        monkeypatch.delenv("PORTSWIGGER_EMAIL", raising=False)
        monkeypatch.delenv("PORTSWIGGER_PASSWORD", raising=False)
        with pytest.raises(PortSwiggerAuthError):
            await spinup_lab(LAB_URL)


class TestSessionPersistence:
    """AC: saved session is reused on re-execution to avoid repeated login."""

    async def test_existing_session_file_loaded_as_cookies(self, tmp_path, monkeypatch):
        """When SESSION_FILE exists, its cookies are passed to add_cookies."""
        fake_cookies = [{"name": "session", "value": "tok123", "domain": "portswigger.net"}]
        session_file = tmp_path / ".portswigger_session.json"
        session_file.write_text(json.dumps(fake_cookies))

        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")

        mock_pw_cm, mock_context, _ = _make_playwright_mock()

        with (
            patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
            patch("tests.evals.spinup.SESSION_FILE", session_file),
            patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=True)),
        ):
            await spinup_lab(LAB_URL)

        mock_context.add_cookies.assert_called_once_with(fake_cookies)

    async def test_no_session_file_skips_add_cookies(self, tmp_path, monkeypatch):
        """When SESSION_FILE does not exist, add_cookies is not called."""
        nonexistent = tmp_path / ".portswigger_session.json"

        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")

        mock_pw_cm, mock_context, _ = _make_playwright_mock()

        with (
            patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
            patch("tests.evals.spinup.SESSION_FILE", nonexistent),
            patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=False)),
            patch("tests.evals.spinup._login", AsyncMock()),
            patch("tests.evals.spinup._save_session", AsyncMock()),
        ):
            await spinup_lab(LAB_URL)

        mock_context.add_cookies.assert_not_called()

    async def test_valid_session_skips_login(self, tmp_path, monkeypatch):
        """When the restored session is valid, _login is never called."""
        fake_cookies = [{"name": "session", "value": "valid", "domain": "portswigger.net"}]
        session_file = tmp_path / ".portswigger_session.json"
        session_file.write_text(json.dumps(fake_cookies))

        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")

        mock_pw_cm, _, _ = _make_playwright_mock()
        mock_login = AsyncMock()

        with (
            patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
            patch("tests.evals.spinup.SESSION_FILE", session_file),
            patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=True)),
            patch("tests.evals.spinup._login", mock_login),
        ):
            await spinup_lab(LAB_URL)

        mock_login.assert_not_called()


class TestSpinupLabReturnsUrl:
    """AC: spinup_lab returns a valid *.web-security-academy.net URL."""

    async def test_returns_instance_url(self, tmp_path, monkeypatch):
        """spinup_lab should return the lab_page.url after navigation."""
        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")

        mock_pw_cm, _, _ = _make_playwright_mock(INSTANCE_URL)

        with (
            patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
            patch("tests.evals.spinup.SESSION_FILE", tmp_path / ".no_session"),
            patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=False)),
            patch("tests.evals.spinup._login", AsyncMock()),
            patch("tests.evals.spinup._save_session", AsyncMock()),
        ):
            result = await spinup_lab(LAB_URL)

        assert "web-security-academy.net" in result
        assert result.startswith("https://")

    async def test_selector_timeout_raises_timeout_error(self, tmp_path, monkeypatch):
        """When the lab launch button never appears, PortSwiggerTimeoutError is raised."""
        monkeypatch.setenv("PORTSWIGGER_EMAIL", "user@example.com")
        monkeypatch.setenv("PORTSWIGGER_PASSWORD", "secret")

        # Minimal mock: error fires before expect_page, so no need for the full chain.
        mock_main_page = AsyncMock()
        mock_main_page.goto = AsyncMock()
        mock_main_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_main_page)
        mock_context.add_cookies = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_obj = MagicMock()
        mock_playwright_obj.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_cm = MagicMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_playwright_obj)
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
            patch("tests.evals.spinup.SESSION_FILE", tmp_path / ".no_session"),
            patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=True)),
            pytest.raises(PortSwiggerTimeoutError, match="Timed out waiting"),
        ):
            await spinup_lab(LAB_URL)

    @pytest.mark.e2e
    async def test_real_spinup_returns_instance_url(self):
        """Real spinup: requires PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD to be set."""
        result = await spinup_lab(LAB_URL)
        assert result.startswith("https://")
        assert "web-security-academy.net" in result
