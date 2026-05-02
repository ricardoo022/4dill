import os
import re
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pentest.database.connection import close_db, get_session, init_db
from pentest.database.models import Base, create_vector_extension
from pentest.tools.guide import create_guide_tools, is_available

pytestmark = pytest.mark.e2e

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
)


async def ensure_test_db_exists(url: str):
    """Ensure the test database exists by creating it if necessary.

    Connects to the default 'postgres' database and runs CREATE DATABASE.
    """
    match = re.search(r"/([^/]+)$", url)
    if not match:
        return
    dbname = match.group(1)

    # Reconstruct URL to connect to the default 'postgres' database
    postgres_url = url.replace(f"/{dbname}", "/postgres")

    # Use isolation_level="AUTOCOMMIT" to run CREATE DATABASE
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
    # Ensure database exists first
    await ensure_test_db_exists(TEST_DATABASE_URL)

    await init_db(TEST_DATABASE_URL, echo=False)

    async with get_session() as session:
        conn = await session.connection()
        # Minimal cleanup for this test
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
    yield
    async with get_session() as session:
        await session.execute(text("DELETE FROM vector_store"))
        await session.commit()
    await close_db()


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set - skipping E2E tests")
    return key


@pytest.fixture
def guide_tools_available(openai_api_key):
    """Ensure Guide tools are available before running E2E tests."""
    # We pass None for db_session just to check the API key part of is_available
    # or we can check is_available implementation details if needed.
    # Since we are in E2E, we know we have a DB session in the test itself.
    if not is_available(db_session=MagicMock()) or openai_api_key == "sk-xxx":
        pytest.skip("Guide tools not available or placeholder OPENAI_API_KEY - skipping E2E tests")


@pytest.mark.asyncio
async def test_guide_store_and_search_e2e(db_session, guide_tools_available):
    """E2E: Store a guide and search for it semantically in a real DB."""
    async with get_session() as session:
        search_tool, store_tool = create_guide_tools(session)

        # 1. Store a guide
        store_args = {
            "guide": "Step 1: Discover target version. Step 2: Search for exploits for 192.168.1.50.",
            "question": "How to perform methodology for target discovery?",
            "type": "pentest",
            "message": "Storing e2e test guide",
            "flow_id": "e2e-flow",
        }
        store_result = await store_tool.arun(store_args)
        assert store_result == "guide stored successfully"

        # 2. Verify it's in the DB with anonymization
        result = await session.execute(text("SELECT content, metadata_ FROM vector_store"))
        rows = result.all()
        assert len(rows) == 1
        content, metadata = rows[0]
        assert "192.168.1.50" not in content
        assert "[IP]" in content
        assert metadata["guide_type"] == "pentest"
        assert metadata["flow_id"] == "e2e-flow"

        # 3. Search for it semantically
        # Using a slightly different query
        search_args = {
            "questions": ["methodology for discovering targets"],
            "type": "pentest",
            "message": "Searching e2e test guide",
        }
        search_result = await search_tool.arun(search_args)

        assert "Found 1 relevant guides" in search_result
        assert "target discovery" in search_result.lower()
        assert "Guide:" in search_result
        assert "[IP]" in search_result


@pytest.mark.asyncio
async def test_search_guide_fallback_e2e(db_session, guide_tools_available):
    """E2E: Verify fallback message when no guide is found."""
    async with get_session() as session:
        search_tool, _ = create_guide_tools(session)

        search_args = {
            "questions": ["non existent methodology"],
            "type": "other",
            "message": "Searching non-existent guide",
        }
        result = await search_tool.arun(search_args)
        assert (
            result
            == "nothing found in guide store and you need to store it after figure out this case"
        )
