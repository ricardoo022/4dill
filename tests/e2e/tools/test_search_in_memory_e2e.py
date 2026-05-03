"""E2E tests for US-081: search_in_memory tool with real OpenAI embeddings and real pgvector.

These tests require:
- OPENAI_API_KEY set in environment (real embeddings, not mocked)
- PostgreSQL reachable at TEST_DATABASE_URL

Run manually: pytest tests/e2e/tools/test_search_in_memory_e2e.py -v -m e2e
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pentest.database.connection import close_db, get_session, init_db
from pentest.database.models import Base, VectorStore, create_vector_extension
from pentest.tools.search_memory import create_search_in_memory_tool

# Load .env from project root so OPENAI_API_KEY and DATABASE_URL are available
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

pytestmark = pytest.mark.e2e

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/lusitaidb",
)


async def ensure_test_db_exists(url: str) -> None:
    """Ensure the test database exists by creating it if necessary."""
    match = re.search(r"/([^/]+)$", url)
    if not match:
        return
    dbname = match.group(1)
    postgres_url = url.replace(f"/{dbname}", "/postgres")
    engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{dbname}'"))
            if not result.scalar():
                await conn.execute(text(f"CREATE DATABASE {dbname}"))
    finally:
        await engine.dispose()


@pytest.fixture()
async def db_schema():
    """Initialize schema for E2E tests."""
    await ensure_test_db_exists(TEST_DATABASE_URL)
    await init_db(TEST_DATABASE_URL, echo=False)
    async with get_session() as session:
        conn = await session.connection()
        await conn.execute(text("DROP TABLE IF EXISTS vector_store CASCADE"))
        await create_vector_extension(conn)
        await conn.run_sync(Base.metadata.create_all)
    await close_db()
    yield
    await close_db()


@pytest.fixture()
async def db_session(db_schema):
    """Provide a fresh database session and clean up afterward."""
    await init_db(TEST_DATABASE_URL, echo=False)
    yield db_session  # Just a marker; session is obtained via get_session() in tests
    async with get_session() as session:
        await session.execute(text("DELETE FROM vector_store"))
        await session.commit()
    await close_db()


@pytest.fixture
def openai_api_key():
    """Skip E2E tests if OPENAI_API_KEY is not set or OpenAI API is unreachable."""
    key = os.getenv("OPENAI_API_KEY")
    if not key or key == "sk-xxx":
        pytest.skip("OPENAI_API_KEY not set or placeholder — skipping E2E tests")
    # Check if OpenAI API is reachable via HTTPS (catches DNS + connectivity)
    import httpx

    try:
        resp = httpx.get("https://api.openai.com/v1/models", timeout=5.0)
        # 401/403 = API is reachable (auth error expected without valid key)
        # Any other response means the API is reachable
        if resp.status_code not in (200, 401, 403):
            pytest.skip(f"OpenAI API returned unexpected status {resp.status_code} — skipping E2E")
    except Exception as e:
        pytest.skip(f"OpenAI API unreachable ({e}) — skipping E2E tests")
    return key


@pytest.fixture
def tool_available(openai_api_key):
    """Skip if embeddings are not available."""
    if not create_search_in_memory_tool(MagicMock()):
        pytest.skip("search_in_memory tool not available — skipping E2E tests")


@pytest.mark.asyncio
async def test_search_in_memory_real_embeddings_round_trip_e2e(db_session, openai_api_key):
    """E2E: 🔁 Full round-trip with real OpenAI embeddings and real pgvector.

    Seeds three distinct security findings, then searches with a semantically
    related query (different wording) and asserts the most relevant result
    is returned with a meaningful similarity score.
    """
    async with get_session() as session:
        # Garante que o modelo instanciado é O MESMO que a ferramenta usa internamente
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        doc_a = "SQL injection vulnerability in login endpoint /api/auth. Payload ' OR 1=1 -- bypasses authentication completely."
        doc_b = "Cross-site scripting (XSS) reflected in search parameter q. Payload <script>alert(document.cookie)</script> executes."
        doc_c = "OpenSSH 8.9p1 on port 22. CVE-2023-38408 allows remote code execution via PKCS#11 forwarded agent."

        emb_a = await embeddings.aembed_query(doc_a)
        emb_b = await embeddings.aembed_query(doc_b)
        emb_c = await embeddings.aembed_query(doc_c)

        session.add_all(
            [
                VectorStore(
                    content=doc_a,
                    metadata_={
                        "doc_type": "vulnerability",
                        "flow_id": "e2e-1",
                        "task_id": 1,  # CORRIGIDO: Era string, agora é integer
                        "subtask_id": 10,  # CORRIGIDO: Era string, agora é integer
                        "question": "sqli in login",
                    },
                    embedding=emb_a,
                ),
                VectorStore(
                    content=doc_b,
                    metadata_={
                        "doc_type": "vulnerability",
                        "flow_id": "e2e-1",
                        "task_id": 2,  # CORRIGIDO: Era string, agora é integer
                        "subtask_id": 20,  # CORRIGIDO: Era string, agora é integer
                        "question": "xss in search",
                    },
                    embedding=emb_b,
                ),
                VectorStore(
                    content=doc_c,
                    metadata_={
                        "doc_type": "finding",
                        "flow_id": "e2e-2",
                        "task_id": 1,  # CORRIGIDO: Era string, agora é integer
                        "subtask_id": 5,  # CORRIGIDO: Era string, agora é integer
                        "question": "ssh version scan",
                    },
                    embedding=emb_c,
                ),
            ]
        )
        await session.commit()

    async with get_session() as session:
        tool = create_search_in_memory_tool(session)

        result = await tool.ainvoke(
            {
                "queries": [
                    "database injection bypass authentication",
                    "sql payload to skip login",
                ],
                "max_results": 3,
                "message": "searching for sqli vulns",
            }
        )

        assert "Found 1 relevant memory entries:" in result
        assert "SQL injection" in result
        assert "login endpoint" in result
        assert "[vulnerability]" in result
        assert "Score: " in result

        score_match = re.search(r"Score: ([0-9]+\.[0-9]+)", result)
        assert score_match is not None
        score = float(score_match.group(1))
        assert score > 0.5, f"Expected meaningful score > 0.5, got {score}"


@pytest.mark.asyncio
async def test_search_in_memory_task_id_filter_real_embeddings_e2e(db_session, openai_api_key):
    """E2E: 🔁 Filter by task_id with real embeddings — results outside scope excluded."""
    async with get_session() as session:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        doc_task1 = "Authentication bypass via JWT none algorithm on /api/auth endpoint"
        doc_task2 = "Rate limiting bypass on password reset /api/reset-password endpoint"

        emb_1 = await embeddings.aembed_query(doc_task1)
        emb_2 = await embeddings.aembed_query(doc_task2)

        session.add_all(
            [
                VectorStore(
                    content=doc_task1,
                    metadata_={
                        "doc_type": "vulnerability",
                        "flow_id": "e2e-filter-1",
                        "task_id": 1,  # CORRIGIDO
                    },
                    embedding=emb_1,
                ),
                VectorStore(
                    content=doc_task2,
                    metadata_={
                        "doc_type": "vulnerability",
                        "flow_id": "e2e-filter-1",
                        "task_id": 2,  # CORRIGIDO
                    },
                    embedding=emb_2,
                ),
            ]
        )
        await session.commit()

    async with get_session() as session:
        tool = create_search_in_memory_tool(session)
        result = await tool.ainvoke(
            {
                "queries": ["authentication bypass vulnerability"],
                "task_id": 1,  # Match com o integer da BD
                "message": "searching task 1 findings",
            }
        )

        assert "JWT none algorithm" in result
        assert "Rate limiting" not in result
        assert "task=1" in result


@pytest.mark.asyncio
async def test_search_in_memory_multi_query_merge_real_embeddings_e2e(db_session, openai_api_key):
    """E2E: 🔁 Multi-query merge with real embeddings and deduplication."""
    async with get_session() as session:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        docs = [
            "SQL injection in /api/users?id= parameter allows UNION-based data extraction from users table",
            "Reflected XSS in search field q parameter. Input not sanitized, script executes in browser",
            "Server-Side Request Forgery (SSRF) via /api/fetch?url= parameter. Can reach internal services on 10.0.0.0/8",
        ]

        embeddings_list = [await embeddings.aembed_query(d) for d in docs]

        session.add_all(
            [
                VectorStore(
                    content=docs[i],
                    metadata_={
                        "doc_type": "vulnerability",
                        "flow_id": "e2e-multi",
                        "task_id": i + 1,  # CORRIGIDO: Removida a conversão para str()
                    },
                    embedding=embeddings_list[i],
                )
                for i in range(3)
            ]
        )
        await session.commit()

    async with get_session() as session:
        tool = create_search_in_memory_tool(session)
        result = await tool.ainvoke(
            {
                "queries": [
                    "sql injection union select",
                    "cross site scripting reflected",
                ],
                "max_results": 5,
                "message": "searching web vulns",
            }
        )

        assert "Found 2 relevant memory entries:" in result
        assert "SQL injection" in result
        assert "XSS" in result or "script executes" in result
        assert "SSRF" not in result

        lines = result.split("\n")
        sqli_line = next((i for i, line in enumerate(lines) if "SQL injection" in line), None)
        xss_line = next(
            (i for i, line in enumerate(lines) if "XSS" in line or "script" in line), None
        )
        assert sqli_line is not None
        assert xss_line is not None
        assert sqli_line < xss_line, "SQL injection should appear before XSS (higher score)"
