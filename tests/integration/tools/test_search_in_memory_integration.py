# File: tests/integration/tools/test_search_in_memory_integration.py
"""Integration tests for US-081: search_in_memory tool with flow/task/subtask filters.

These tests require a running PostgreSQL database with pgvector extension.
They use the devcontainer/test database directly (not testcontainers).
"""

from __future__ import annotations

import os
import socket
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest

from pentest.database.connection import get_session
from pentest.database.models import VectorStore
from pentest.tools.search_memory import create_search_in_memory_tool


def is_db_reachable() -> bool:
    """Check if the test database is reachable via TCP."""
    db_url = os.getenv(
        "DATABASE_URL",
        os.getenv(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
        ),
    )
    try:
        parsed = urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except (OSError, socket.gaierror):
        return False


@pytest.mark.skipif(
    not is_db_reachable(), reason="Database not reachable (e.g. 'db' host unknown or down)"
)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_round_trip_real_pgvector(db_session):
    """US-081: 🔁 Round-trip with real pgvector similarity search.

    Inserts 3 documents with known embeddings, searches with a matching
    query vector, and asserts that the most relevant result is returned.
    """
    query_vector = [1.0] + [0.0] * 1535

    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        mock_emb.aembed_query = AsyncMock(return_value=query_vector)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                session.add_all(
                    [
                        VectorStore(
                            content="SQL Injection: The login form at /api/auth accepts unparameterized input in the 'username' field. Payload: ' OR 1=1 -- bypasses authentication.",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "100",
                                "task_id": "1",
                                "subtask_id": "10",
                                "question": "what sqli vulns were found",
                            },
                            embedding=[1.0] + [0.0] * 1535,  # Distance 0.0
                        ),
                        VectorStore(
                            content="Nmap scan results: Ports 22 (OpenSSH 8.9), 80 (Apache 2.4.52), 443 (HTTPS), 5432 (PostgreSQL 16.1) are open.",
                            metadata_={
                                "doc_type": "finding",
                                "flow_id": "100",
                                "task_id": "1",
                                "question": "what ports are open",
                            },
                            # Orthogonal to query [1,0,0,...]: distance = 1.0 (>0.35 threshold)
                            embedding=[0.0, 1.0] + [0.0] * 1534,
                        ),
                        VectorStore(
                            content="XSS reflected in search parameter q. Payload: <script>alert(1)</script> executed in victim browser.",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "100",
                                "task_id": "2",
                                "subtask_id": "20",
                                "question": "xss findings",
                            },
                            # Orthogonal to query [1,0,0,...]: distance = 1.0 (>0.35 threshold)
                            embedding=[0.0, 0.0, 1.0] + [0.0] * 1533,
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                tool = create_search_in_memory_tool(session)
                result = await tool.ainvoke(
                    {
                        "queries": ["sql injection login form"],
                        "message": "searching for sqli findings",
                    }
                )

                assert "Found 1 relevant memory entries:" in result
                assert "SQL Injection" in result
                assert "[Score: 1.00]" in result
                assert "[vulnerability]" in result
                assert "Nmap scan" not in result
                assert "XSS" not in result


@pytest.mark.skipif(not is_db_reachable(), reason="Database not reachable")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_multi_query_merge(db_session):
    """US-081: 🔁 Multi-query merge with deduplication on real pgvector.

    Seeds 4 documents, searches with 2 different queries that return
    overlapping results, and verifies merge + dedup + sorting.
    """
    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        mock_emb.aembed_query = AsyncMock(return_value=[0.5] * 1536)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                session.add_all(
                    [
                        VectorStore(
                            content="OpenSSH 8.9 CVE-2023-38408 allows remote code execution via forwarded agent",
                            metadata_={"doc_type": "vulnerability", "flow_id": "200"},
                            embedding=[0.5] * 1536,  # Distance 0.0
                        ),
                        VectorStore(
                            content="Apache 2.4.52 path traversal CVE-2024-7890",
                            metadata_={"doc_type": "vulnerability", "flow_id": "200"},
                            embedding=[0.5] * 1536,  # Distance 0.0 (same vector)
                        ),
                        VectorStore(
                            content="PostgreSQL 16.1 has no known critical CVEs as of 2024",
                            metadata_={"doc_type": "finding", "flow_id": "200"},
                            embedding=[0.5] * 1536,  # Distance 0.0
                        ),
                        VectorStore(
                            content="HTTP/2 Rapid Reset attack (CVE-2023-44487) affects nginx",
                            metadata_={"doc_type": "vulnerability", "flow_id": "200"},
                            embedding=[0.5] * 1536,  # Distance 0.0
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                tool = create_search_in_memory_tool(session)
                result = await tool.ainvoke(
                    {
                        "queries": ["ssh vulnerability", "web server exploit"],
                        "max_results": 10,
                        "message": "searching for vulns",
                    }
                )

                assert "Found 4 relevant memory entries:" in result
                assert "OpenSSH" in result
                assert "Apache" in result
                assert "PostgreSQL" in result
                assert "HTTP/2" in result


@pytest.mark.skipif(not is_db_reachable(), reason="Database not reachable")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_task_id_filter(db_session):
    """US-081: 🔁 Filter by task_id — results outside scope do not appear.

    Seeds documents with task_id=1 and task_id=2, searches with
    task_id=1 filter, and asserts only task_id=1 results appear.
    """
    query_vector = [1.0] + [0.0] * 1535

    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        mock_emb.aembed_query = AsyncMock(return_value=query_vector)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                session.add_all(
                    [
                        VectorStore(
                            content="Task 1 finding: SQL injection in login endpoint",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "300",
                                "task_id": "1",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                        VectorStore(
                            content="Task 2 finding: XSS in search form",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "300",
                                "task_id": "2",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                tool = create_search_in_memory_tool(session)
                result = await tool.ainvoke(
                    {
                        "queries": ["injection"],
                        "task_id": 1,
                        "message": "searching task 1 findings",
                    }
                )

                assert "Task 1 finding" in result
                assert "Task 2 finding" not in result


@pytest.mark.skipif(not is_db_reachable(), reason="Database not reachable")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_subtask_id_filter(db_session):
    """US-081: 🔁 Filter by subtask_id — results outside scope do not appear.

    Seeds documents with subtask_id=10 and subtask_id=20, searches with
    subtask_id=10 filter, and asserts only subtask_id=10 results appear.
    """
    query_vector = [1.0] + [0.0] * 1535

    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        mock_emb.aembed_query = AsyncMock(return_value=query_vector)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                session.add_all(
                    [
                        VectorStore(
                            content="Subtask 10: Nmap found port 22 open",
                            metadata_={
                                "doc_type": "finding",
                                "flow_id": "400",
                                "subtask_id": "10",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                        VectorStore(
                            content="Subtask 20: SQLmap confirmed injection",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "400",
                                "subtask_id": "20",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                tool = create_search_in_memory_tool(session)
                result = await tool.ainvoke(
                    {
                        "queries": ["scan results"],
                        "subtask_id": 10,
                        "message": "searching subtask 10",
                    }
                )

                assert "Subtask 10" in result
                assert "Subtask 20" not in result


@pytest.mark.skipif(not is_db_reachable(), reason="Database not reachable")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_no_openai_key_integration(db_session):
    """US-081: Fallback when OPENAI_API_KEY is not set — explicit message, no crash."""
    with patch.dict(os.environ, {}, clear=True):
        async with get_session() as session:
            tool = create_search_in_memory_tool(session)
            result = await tool.ainvoke({"queries": ["test"], "message": "searching..."})
            assert "embeddings not configured - set OPENAI_API_KEY" in result


@pytest.mark.skipif(not is_db_reachable(), reason="Database not reachable")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_in_memory_combined_filters(db_session):
    """US-081: 🔁 Combined task_id + subtask_id filter returns only matching documents.

    Seeds documents with different task/subtask combinations and verifies
    that both filters must match for a result to appear.
    """
    query_vector = [1.0] + [0.0] * 1535

    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        mock_emb.aembed_query = AsyncMock(return_value=query_vector)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                session.add_all(
                    [
                        VectorStore(
                            content="Task 1 / Subtask 5: Auth bypass via JWT none algorithm",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "500",
                                "task_id": "1",
                                "subtask_id": "5",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                        VectorStore(
                            content="Task 1 / Subtask 10: CSRF token missing on profile update",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "500",
                                "task_id": "1",
                                "subtask_id": "10",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                        VectorStore(
                            content="Task 2 / Subtask 5: Rate limiting bypass on password reset",
                            metadata_={
                                "doc_type": "vulnerability",
                                "flow_id": "500",
                                "task_id": "2",
                                "subtask_id": "5",
                            },
                            embedding=[1.0] + [0.0] * 1535,
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                tool = create_search_in_memory_tool(session)
                result = await tool.ainvoke(
                    {
                        "queries": ["auth vulnerability"],
                        "task_id": 1,
                        "subtask_id": 5,
                        "message": "searching specific scope",
                    }
                )

                assert "Auth bypass via JWT" in result
                assert "CSRF token" not in result
                assert "Rate limiting" not in result
