"""Unit tests for Firebase detection."""

from __future__ import annotations

import pytest
import respx
from src.pentest.models.recon import FirebaseDetectionResult
from src.pentest.recon.firebase import detect_firebase

HTML_WITH_SCRIPT = """
<html>
<head>
<script src="/static/main.js"></script>
</head>
<body></body>
</html>
"""

JS_FULL_CONFIG = """
var firebaseConfig = {
  apiKey: 'FAKE_API_KEY_123',
  authDomain: 'demo.firebaseapp.com',
  projectId: 'demo-project',
  storageBucket: 'demo.appspot.com',
  messagingSenderId: '1234567890',
  appId: '1:123:web:abcdef'
};
firebase.initializeApp(firebaseConfig);
"""

JS_PARTIAL_CONFIG = """
var firebaseConfig = {
  authDomain: 'demo.firebaseapp.com',
  storageBucket: 'demo.appspot.com'
};
"""

JS_NO_PATTERNS = "console.log('safe');"


@pytest.mark.asyncio
@respx.mock
async def test_full_config_high_confidence():
    base = "https://site.example"
    respx.get("https://site.example/").respond(200, text=HTML_WITH_SCRIPT)
    respx.get("https://site.example/static/main.js").respond(200, text=JS_FULL_CONFIG)

    res = await detect_firebase(base)
    assert isinstance(res, FirebaseDetectionResult)
    assert res.confidence == "high"
    assert res.api_key == "FAKE_API_KEY_123"
    assert res.project_id == "demo-project"


@pytest.mark.asyncio
@respx.mock
async def test_partial_config_medium_confidence():
    base = "https://site2.example"
    respx.get("https://site2.example/").respond(200, text=HTML_WITH_SCRIPT)
    respx.get("https://site2.example/static/main.js").respond(200, text=JS_PARTIAL_CONFIG)

    res = await detect_firebase(base)
    assert isinstance(res, FirebaseDetectionResult)
    assert res.confidence == "medium"
    assert res.api_key is None
    assert res.project_id is None


@pytest.mark.asyncio
@respx.mock
async def test_no_patterns_returns_none():
    base = "https://clean.example"
    respx.get("https://clean.example/").respond(200, text=HTML_WITH_SCRIPT)
    respx.get("https://clean.example/static/main.js").respond(200, text=JS_NO_PATTERNS)

    res = await detect_firebase(base)
    assert res is None
