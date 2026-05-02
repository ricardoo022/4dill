# File: tests/integration/tools/test_search_memory.py
from __future__ import annotations

import os
import socket
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest

from pentest.database.connection import get_session
from pentest.database.models import VectorStore
from pentest.tools.search_memory import create_search_answer_tool


def is_db_reachable() -> bool:
    """Check if the test database is reachable via TCP."""
    # Use the same logic as tests/integration/database/conftest.py to get the URL
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
@pytest.mark.asyncio
async def test_search_answer_integration_real_db(db_session):
    """US-058: Integration test with real pgvector similarity search."""
    # Mock embeddings to avoid external API calls and ensure deterministic vectors
    with patch("pentest.tools.search_memory.OpenAIEmbeddings") as mock_emb_cls:
        mock_emb = mock_emb_cls.return_value
        # Query vector: [1.0, 0.0, ...]
        query_vector = [1.0] + [0.0] * 1535
        mock_emb.aembed_query = AsyncMock(return_value=query_vector)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            async with get_session() as session:
                # Add test documents to vector_store
                session.add_all(
                    [
                        VectorStore(
                            content="Correct Answer Guide: SQL Injection testing steps",
                            metadata_={
                                "doc_type": "answer",
                                "answer_type": "guide",
                                "question": "how to exploit xss",
                            },
                            embedding=[1.0] + [0.0] * 1535,  # Distance 0.0
                        ),
                        VectorStore(
                            content="Wrong Type: Vulnerability report for XSS",
                            metadata_={
                                "doc_type": "answer",
                                "answer_type": "vulnerability",
                                "question": "xss found",
                            },
                            embedding=[1.0] + [0.0] * 1535,  # Distance 0.0, but wrong answer_type
                        ),
                        VectorStore(
                            content="Too Far Away: Unrelated content",
                            metadata_={
                                "doc_type": "answer",
                                "answer_type": "guide",
                                "question": "unrelated",
                            },
                            # Distance approx 0.3 (1 - 0.7), threshold is 0.2
                            embedding=[0.7, 0.7] + [0.0] * 1534,
                        ),
                    ]
                )
                await session.commit()

            async with get_session() as session:
                # Create tool with active session
                tool = create_search_answer_tool(session)

                # Invoke tool
                result = await tool.ainvoke(
                    {
                        "questions": ["how to exploit xss"],
                        "type": "guide",
                        "message": "searching...",
                    }
                )

                # Validate results
                assert "Found 1 relevant answers:" in result
                assert "Correct Answer Guide" in result
                assert "Wrong Type" not in result
                assert "Too Far Away" not in result
                assert "[Score: 1.00]" in result
