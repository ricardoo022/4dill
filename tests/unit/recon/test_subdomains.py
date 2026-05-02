"""Unit tests for subdomain discovery."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest
import respx
from src.pentest.recon.subdomains import discover_subdomains


@pytest.mark.asyncio
@respx.mock
async def test_discover_common_prefixes_and_links(monkeypatch):
    domain = "example.com"
    base = "https://example.com/"
    # Mock main page with links to app.example.com and api.example.com
    html = '<a href="https://app.example.com/">app</a><a href="https://api.example.com/">api</a>'
    respx.get(base).respond(200, text=html)
    # Mock probes for prefixed domains
    respx.get("https://app.example.com/").respond(200, text="OK", headers={"Server": "nginx"})
    respx.get("https://api.example.com/").respond(
        200, text="OK", headers={"Server": "uvicorn", "X-Powered-By": "FastAPI"}
    )
    respx.get("https://admin.example.com/").respond(404)

    # Mock DNS resolution
    monkeypatch.setattr(socket, "gethostbyname", lambda h: "1.2.3.4")

    res = await discover_subdomains(domain)
    # Should include app and api
    urls = {s.url for s in res}
    assert "https://app.example.com" in urls or "https://app.example.com/" in urls
    assert "https://api.example.com" in urls or "https://api.example.com/" in urls
    # Check extracted metadata
    for s in res:
        if "api.example.com" in s.url:
            assert s.server and "uvicorn" in s.server.lower()
            assert s.framework_hint and "fastapi" in s.framework_hint.lower()


@pytest.mark.asyncio
@patch("src.pentest.recon.subdomains._extract_sans")
@respx.mock
async def test_sans_and_probe(mock_sans):
    domain = "example.org"
    mock_sans.return_value = ["api.example.org", "dashboard.example.org"]
    respx.get("https://example.org/").respond(200, text='<a href="https://other.example.org">x</a>')
    respx.get("https://api.example.org/").respond(200, text="OK", headers={"Server": "nginx"})
    respx.get("https://dashboard.example.org/").respond(200, text="OK", headers={"Server": "nginx"})

    # Mock DNS
    with patch("socket.gethostbyname", lambda h: "2.2.2.2"):
        res = await discover_subdomains(domain)

    hosts = {r.url for r in res}
    assert any("api.example.org" in u for u in hosts)
    assert any("dashboard.example.org" in u for u in hosts)


@pytest.mark.asyncio
@respx.mock
async def test_subdomain_401_and_wildcard_sans(monkeypatch):
    domain = "wild.example"
    base = "https://wild.example/"
    html = '<a href="https://secure.wild.example/">secure</a>'
    respx.get(base).respond(200, text=html)
    respx.get("https://secure.wild.example/").respond(
        401, text="Unauthorized", headers={"Server": "nginx"}
    )

    # SAN includes a wildcard entry which should be ignored
    with patch(
        "src.pentest.recon.subdomains._extract_sans",
        return_value=["*.wild.example", "api.wild.example"],
    ):
        # Mock api.wild.example probe
        respx.get("https://api.wild.example/").respond(200, text="OK", headers={"Server": "nginx"})
        monkeypatch.setattr(socket, "gethostbyname", lambda h: "5.6.7.8")
        res = await discover_subdomains(domain)

    urls = {s.url for s in res}
    # secure.wild.example returned 401 and should be kept
    assert any("secure.wild.example" in u for u in urls)
    # wildcard SAN should be ignored; api.wild.example should be discovered
    assert any("api.wild.example" in u for u in urls)
