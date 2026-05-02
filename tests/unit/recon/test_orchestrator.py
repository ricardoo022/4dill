"""Unit tests for the backend orchestrator.

Tests mock the individual detectors and subdomain discovery to focus on
orchestration logic and selection rules.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from src.pentest.models.recon import BackendProfile, SubdomainInfo
from src.pentest.recon.orchestrator import run_backend_detection


@pytest.mark.asyncio
async def test_main_has_supabase():
    url = "https://example.com"

    # Mock discover_subdomains to return empty
    with patch("src.pentest.recon.orchestrator.discover_subdomains", AsyncMock(return_value=[])):
        # Mock detect_supabase to return a high confidence result
        sup = AsyncMock()
        sup.return_value = type(
            "R",
            (),
            {
                "confidence": "high",
                "url": "https://abc.supabase.co",
                "anon_key": "eyJ...",
            },
        )()
        with (
            patch(
                "src.pentest.recon.orchestrator.detect_supabase",
                AsyncMock(return_value=sup.return_value),
            ),
            patch(
                "src.pentest.recon.orchestrator.detect_firebase",
                AsyncMock(return_value=None),
            ),
            patch(
                "src.pentest.recon.orchestrator.detect_custom_api",
                AsyncMock(return_value=None),
            ),
        ):
            profile = await run_backend_detection(url)

    assert isinstance(profile, BackendProfile)
    assert profile.backend_type == "supabase"
    assert profile.primary_target == url
    assert profile.confidence == "high"
    assert "fase-21" in profile.scan_path


@pytest.mark.asyncio
async def test_subdomain_has_firebase():
    url = "https://marketing.example"
    sub = SubdomainInfo(
        url="https://app.example",
        status=200,
        ip_address="1.2.3.4",
        server="nginx",
        framework_hint=None,
    )

    with (
        patch(
            "src.pentest.recon.orchestrator.discover_subdomains",
            AsyncMock(return_value=[sub]),
        ),
        patch(
            "src.pentest.recon.orchestrator.detect_supabase",
            AsyncMock(return_value=None),
        ),
    ):
        firebase_res = type(
            "F", (), {"confidence": "high", "api_key": "FAKE", "project_id": "demo"}
        )()
        with (
            patch(
                "src.pentest.recon.orchestrator.detect_firebase",
                AsyncMock(return_value=firebase_res),
            ),
            patch(
                "src.pentest.recon.orchestrator.detect_custom_api",
                AsyncMock(return_value=None),
            ),
        ):
            profile = await run_backend_detection(url)

    assert profile.primary_target == sub.url
    assert profile.backend_type == "firebase"
    assert profile.confidence == "high"
    assert "fase-11" in profile.scan_path


@pytest.mark.asyncio
async def test_unknown_backend():
    url = "https://nothing.example"
    with (
        patch("src.pentest.recon.orchestrator.discover_subdomains", AsyncMock(return_value=[])),
        patch(
            "src.pentest.recon.orchestrator.detect_supabase",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.pentest.recon.orchestrator.detect_firebase",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.pentest.recon.orchestrator.detect_custom_api",
            AsyncMock(return_value=None),
        ),
    ):
        profile = await run_backend_detection(url)

    assert profile.backend_type == "unknown"
    assert profile.scan_path == ["fase-1", "fase-7"]
