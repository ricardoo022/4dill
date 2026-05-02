"""Unit tests for Supabase detection.

These tests use respx to mock HTTP responses for the page HTML,
JS bundles, and the Supabase REST verification endpoint.
"""

from __future__ import annotations

import pytest
import respx
from src.pentest.models.recon import SupabaseDetectionResult
from src.pentest.recon.supabase import detect_supabase

HTML_WITH_SCRIPTS = """
<html>
<head>
<script src="/static/app.bundle.js"></script>
</head>
<body>OK</body>
</html>
"""

JS_WITH_PATTERNS = (
    'const SUPABASE_URL = "https://demo123.supabase.co";\n'
    'const ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcDEFghijklMNOpqrstUV";'
)

JS_NO_PATTERNS = "console.log('nothing here');"


@pytest.mark.asyncio
@respx.mock
async def test_detect_high_confidence():
    base = "https://example.com"
    # Mock HTML
    respx.get("https://example.com/").respond(200, text=HTML_WITH_SCRIPTS)
    # Mock js bundle
    respx.get("https://example.com/static/app.bundle.js").respond(200, text=JS_WITH_PATTERNS)
    # Mock verification endpoint returning 200
    respx.get("https://demo123.supabase.co/rest/v1/").respond(200, text="[]")

    result = await detect_supabase(base)
    assert isinstance(result, SupabaseDetectionResult)
    assert result.confidence == "high"
    assert result.project_id == "demo123"
    assert result.anon_key.startswith("eyJhbGci")


@pytest.mark.asyncio
@respx.mock
async def test_detect_low_confidence():
    base = "https://example.org"
    respx.get("https://example.org/").respond(200, text=HTML_WITH_SCRIPTS)
    respx.get("https://example.org/static/app.bundle.js").respond(200, text=JS_WITH_PATTERNS)
    # Verification endpoint returns 404
    respx.get("https://demo123.supabase.co/rest/v1/").respond(404, text="not found")

    result = await detect_supabase(base)
    assert isinstance(result, SupabaseDetectionResult)
    assert result.confidence == "low"


@pytest.mark.asyncio
@respx.mock
async def test_detect_none_when_no_patterns():
    base = "https://nope.example"
    respx.get("https://nope.example/").respond(200, text=HTML_WITH_SCRIPTS)
    respx.get("https://nope.example/static/app.bundle.js").respond(200, text=JS_NO_PATTERNS)

    result = await detect_supabase(base)
    assert result is None
