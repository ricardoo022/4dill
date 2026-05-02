"""Unit tests for custom API / framework detection."""

from __future__ import annotations

import pytest
import respx
from src.pentest.models.recon import CustomApiDetectionResult, GraphQLDetectionResult
from src.pentest.recon.custom_api import detect_custom_api

HTML_NEXT = """
<html><head><script src="/_next/static/app.js"></script></head><body></body></html>
"""

HTML_API_HINT = """
<html><body><a href="/api/v1/status">status</a></body></html>
"""


@pytest.mark.asyncio
@respx.mock
async def test_graphql_detection():
    base = "https://gql.example"
    respx.get("https://gql.example/").respond(200, text="OK")
    respx.post("https://gql.example/graphql").respond(200, json={"data": {"__typename": "Query"}})

    res = await detect_custom_api(base)
    assert isinstance(res, GraphQLDetectionResult)
    assert res.endpoint == "/graphql"
    assert res.confidence == "high"


@pytest.mark.asyncio
@respx.mock
async def test_openapi_detection():
    base = "https://api.example"
    respx.get("https://api.example/").respond(200, text=HTML_API_HINT)
    # openapi.json responds with a basic schema
    respx.get("https://api.example/openapi.json").respond(
        200, json={"openapi": "3.0.0", "paths": {}}
    )

    res = await detect_custom_api(base)
    assert isinstance(res, CustomApiDetectionResult)
    assert res.framework == "fastapi"
    assert res.confidence == "high"


@pytest.mark.asyncio
@respx.mock
async def test_header_and_html_hints():
    base = "https://next.example"
    respx.get("https://next.example/").respond(
        200, headers={"X-Powered-By": "Next.js"}, text=HTML_NEXT
    )

    res = await detect_custom_api(base)
    assert isinstance(res, CustomApiDetectionResult)
    assert "nextjs" in res.framework or res.framework == "next.js" or res.framework == "next"
    assert res.confidence in ("medium", "low")


@pytest.mark.asyncio
@respx.mock
async def test_meteor_detection_and_sockjs():
    base = "https://meteor.example"
    # HTML contains METEOR@ hint
    respx.get("https://meteor.example/").respond(200, text="Some code METEOR@1.0")
    res = await detect_custom_api(base)
    assert isinstance(res, CustomApiDetectionResult)
    assert res.framework == "meteor"

    # Now mock sockjs info endpoint returning websocket data
    respx.get("https://meteor2.example/").respond(200, text="OK")
    respx.get("https://meteor2.example/sockjs/info").respond(200, json={"websocket": True})
    res2 = await detect_custom_api("https://meteor2.example")
    assert isinstance(res2, CustomApiDetectionResult)
    assert res2.framework == "meteor"


@pytest.mark.asyncio
@respx.mock
async def test_cookie_based_detection():
    base = "https://django.example"
    respx.get(base).respond(
        200, headers={"Set-Cookie": "csrftoken=abc123; Path=/; HttpOnly"}, text="OK"
    )
    res = await detect_custom_api(base)
    assert isinstance(res, CustomApiDetectionResult)
    assert res.framework == "django"
