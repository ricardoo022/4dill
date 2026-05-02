"""E2E tests for PortSwigger lab spinup against the real website (US-046).

These tests require real credentials and a live internet connection:
    PORTSWIGGER_EMAIL    — PortSwigger account email
    PORTSWIGGER_PASSWORD — PortSwigger account password

Run manually (never in CI):
    pytest tests/evals/test_spinup_e2e.py -v -m e2e

Estimated runtime: ~4–6 minutes (real browser spinups).
"""

import json

import pytest

from tests.evals.spinup import (
    LABS_FILE,
    SESSION_FILE,
    PortSwiggerAuthError,
    _load_credentials,
    spinup_batch,
    spinup_lab,
)

# Quick subset lab IDs and URLs loaded from portswigger_mvp.json
with open(LABS_FILE) as _f:
    _DATASET = json.load(_f)

_QUICK_LAB_IDS: list[str] = _DATASET["subsets"]["quick"]["labs"]
_LABS_BY_ID: dict[str, dict] = {lab["lab_id"]: lab for lab in _DATASET["labs"]}

# First quick lab used in single-lab tests
_SQLI_LAB = _LABS_BY_ID["sqli-login-bypass"]
_XSS_LAB = _LABS_BY_ID["xss-reflected-html-nothing-encoded"]


@pytest.mark.e2e
async def test_sqli_login_bypass_spinup_returns_instance_url():
    """🔁 spinup_lab returns a real *.web-security-academy.net URL for a known lab.

    AC: spinup_lab(lab_url) retorna URL única *.web-security-academy.net
    Tests Required: Spinup de 1 lab conhecido retorna URL válida
    """
    lab_url = _SQLI_LAB["lab_url"]

    result = await spinup_lab(lab_url)

    assert result.startswith("https://"), f"Expected https:// URL, got: {result!r}"
    assert "web-security-academy.net" in result, (
        f"Expected *.web-security-academy.net instance URL, got: {result!r}"
    )
    # The instance URL must NOT be the canonical lab page itself
    assert "portswigger.net" not in result, (
        f"Got canonical page URL instead of instance URL: {result!r}"
    )


@pytest.mark.e2e
async def test_session_persisted_and_reused_on_second_spinup():
    """🔁 SESSION_FILE is written after first spinup and NOT re-written on second spinup.

    AC: Sessão persistida em ficheiro local para evitar login repetido
    Tests Required: Reexecução usa sessão guardada

    Round-trip:
      1. Remove any stale session file
      2. Spin up first lab → SESSION_FILE created, contains valid cookies
      3. Record SESSION_FILE mtime
      4. Immediately spin up second lab (session still valid)
      5. Assert SESSION_FILE mtime unchanged → _save_session was not called → login was skipped
    """
    # 1. Start from a clean state
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    first_lab_url = _SQLI_LAB["lab_url"]
    second_lab_url = _XSS_LAB["lab_url"]

    # 2. First spinup — must log in and write SESSION_FILE
    result_1 = await spinup_lab(first_lab_url)
    assert "web-security-academy.net" in result_1, (
        f"First spinup returned unexpected URL: {result_1!r}"
    )
    assert SESSION_FILE.exists(), (
        "SESSION_FILE was not created after first spinup — session persistence is broken"
    )

    # Verify cookies are valid JSON and non-empty
    cookies = json.loads(SESSION_FILE.read_text())
    assert isinstance(cookies, list) and len(cookies) > 0, (
        f"SESSION_FILE contains unexpected content: {cookies!r}"
    )
    assert any(c.get("domain", "").endswith("portswigger.net") for c in cookies), (
        "No portswigger.net cookie found in saved session"
    )

    # 3. Record mtime before second spinup
    mtime_before = SESSION_FILE.stat().st_mtime_ns

    # 4. Second spinup — session should be reused, no re-login
    result_2 = await spinup_lab(second_lab_url)
    assert "web-security-academy.net" in result_2, (
        f"Second spinup returned unexpected URL: {result_2!r}"
    )

    # 5. SESSION_FILE must NOT have been re-written (login was skipped)
    mtime_after = SESSION_FILE.stat().st_mtime_ns
    assert mtime_after == mtime_before, (
        "SESSION_FILE was re-written during second spinup — login was repeated instead of "
        "reusing the saved session. Check _is_logged_in() and cookie restore logic."
    )


@pytest.mark.e2e
async def test_spinup_batch_quick_subset_returns_all_urls():
    """🔁 spinup_batch spins up all 4 quick subset labs and returns valid instance URLs for each.

    AC: Runner consegue fazer spinup em batch para subset 'quick'

    Round-trip: for each lab in quick subset → spinup → assert real instance URL returned
    """
    results = await spinup_batch(_QUICK_LAB_IDS)

    # All 4 lab IDs must appear in the result dict
    assert set(results.keys()) == set(_QUICK_LAB_IDS), (
        f"Batch result keys {set(results.keys())} do not match expected {set(_QUICK_LAB_IDS)}"
    )

    failed = []
    for lab_id in _QUICK_LAB_IDS:
        url = results[lab_id]
        if not url:
            failed.append(f"{lab_id}: empty URL (spinup failed)")
        elif "web-security-academy.net" not in url:
            failed.append(f"{lab_id}: unexpected URL {url!r}")
        elif not url.startswith("https://"):
            failed.append(f"{lab_id}: URL not https: {url!r}")

    assert not failed, "Batch spinup failures:\n" + "\n".join(f"  - {f}" for f in failed)


@pytest.mark.e2e
def test_missing_credentials_raise_auth_error_before_browser_launch(monkeypatch):
    """PortSwiggerAuthError is raised immediately when credentials are missing.

    AC: Erros de auth/timeouts retornam mensagens claras para troubleshooting
    Tests Required: Falha de credenciais é detectada sem crash silencioso

    This test runs instantly — no browser is launched when credentials are absent.
    """
    monkeypatch.delenv("PORTSWIGGER_EMAIL", raising=False)
    monkeypatch.delenv("PORTSWIGGER_PASSWORD", raising=False)

    with pytest.raises(PortSwiggerAuthError) as exc_info:
        _load_credentials()

    message = str(exc_info.value)
    assert "PORTSWIGGER_EMAIL" in message, (
        f"Error message does not name PORTSWIGGER_EMAIL: {message!r}"
    )
    assert "PORTSWIGGER_PASSWORD" in message, (
        f"Error message does not name PORTSWIGGER_PASSWORD: {message!r}"
    )
    # Proof: error is not a silent crash — it's a typed exception with actionable text
    assert len(message) > 20, f"Error message is too terse to be useful: {message!r}"
