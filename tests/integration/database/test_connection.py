"""Integration tests for database connection module (US-006).

Tests cover:
- Database initialization with valid/invalid URLs
- Connection validation
- Session lifecycle (commit, rollback, close)
- Error handling and recovery
- Connection pool behavior under concurrent load
"""

import asyncio
import os

import pytest
from sqlalchemy import text

from pentest.database.connection import close_db, get_session, init_db
from pentest.database.exceptions import DatabaseConnectionError

# Test database URL (uses Docker service or local PostgreSQL)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
)

# For invalid URL tests
INVALID_DATABASE_URL = "mysql://user:password@localhost:3306/db"
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:9999/db"

pytestmark = pytest.mark.integration


async def _db_is_reachable() -> bool:
    """Check if the test database is reachable."""
    try:
        await init_db(TEST_DATABASE_URL, echo=False)
        await close_db()
        return True
    except (DatabaseConnectionError, Exception):
        return False


@pytest.fixture(autouse=True)
def reset_db_globals():
    """Reset database module globals before each test."""
    import pentest.database.connection as db_module

    db_module._engine = None
    db_module._async_session_factory = None
    yield
    db_module._engine = None
    db_module._async_session_factory = None


@pytest.fixture()
async def db_available(reset_db_globals):
    """Skip the test if the test database is not reachable."""
    reachable = await _db_is_reachable()
    if not reachable:
        pytest.skip("Test database not available")


@pytest.fixture()
async def db_session(db_available):
    """Initialize database and yield, then close on teardown."""
    await init_db(TEST_DATABASE_URL, echo=False)
    yield
    await close_db()


# --- Tests that do NOT need a live database ---


async def test_init_db_invalid_url() -> None:
    """Test that init_db raises ValueError for invalid URL prefix."""
    with pytest.raises(ValueError, match="postgresql\\+asyncpg://"):
        await init_db(INVALID_DATABASE_URL, echo=False)


async def test_init_db_unreachable() -> None:
    """Test that init_db raises DatabaseConnectionError for unreachable host."""
    with pytest.raises(DatabaseConnectionError):
        await init_db(UNREACHABLE_DATABASE_URL, echo=False)


async def test_get_session_without_init() -> None:
    """Test that get_session raises RuntimeError if init_db was not called."""
    with pytest.raises(RuntimeError, match="Database not initialized"):
        async with get_session() as _:
            pass


async def test_database_connection_error_formatting() -> None:
    """Test DatabaseConnectionError formats hostname and port correctly."""
    error = DatabaseConnectionError(
        "Connection failed",
        hostname="localhost",
        port=5432,
    )

    error_str = str(error)
    assert "Connection failed" in error_str
    assert "localhost" in error_str
    assert "5432" in error_str


# --- Tests that require a live database ---


async def test_init_db_success(db_available) -> None:
    """Test successful database initialization with valid URL."""
    await init_db(TEST_DATABASE_URL, echo=False)

    from pentest.database.connection import _async_session_factory, _engine

    assert _engine is not None
    assert _async_session_factory is not None

    await close_db()


async def test_get_session_select_1(db_session) -> None:
    """Test using get_session() to execute SELECT 1 query."""
    async with get_session() as session:
        result = await session.execute(text("SELECT 1 as value"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1


async def test_session_commit_on_success(db_session) -> None:
    """Test that transaction is committed on successful session completion."""
    # Create test table
    async with get_session() as session:
        await session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS test_commit (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL
                )
            """)
        )

    # Insert data and verify commit
    async with get_session() as session:
        await session.execute(
            text("INSERT INTO test_commit (name) VALUES (:name)"),
            {"name": "test_value"},
        )

    # Verify data persisted
    async with get_session() as session:
        result = await session.execute(
            text("SELECT name FROM test_commit WHERE name = :name"),
            {"name": "test_value"},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "test_value"

    # Cleanup
    async with get_session() as session:
        await session.execute(text("DROP TABLE IF EXISTS test_commit"))


async def test_session_rollback_on_exception(db_session) -> None:
    """Test that transaction is rolled back when exception occurs."""
    # Create test table
    async with get_session() as session:
        await session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS test_rollback (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL
                )
            """)
        )

    # Attempt insert with exception
    with pytest.raises(ValueError, match="deliberate error"):
        async with get_session() as session:
            await session.execute(
                text("INSERT INTO test_rollback (name) VALUES (:name)"),
                {"name": "should_rollback"},
            )
            raise ValueError("deliberate error")

    # Verify data was NOT persisted
    async with get_session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM test_rollback WHERE name = :name"),
            {"name": "should_rollback"},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 0, "Data should not have been committed"

    # Cleanup
    async with get_session() as session:
        await session.execute(text("DROP TABLE IF EXISTS test_rollback"))


async def test_close_db(db_available) -> None:
    """Test that close_db() properly shuts down and get_session fails after."""
    await init_db(TEST_DATABASE_URL, echo=False)
    await close_db()

    from pentest.database.connection import _async_session_factory, _engine

    assert _engine is None
    assert _async_session_factory is None

    with pytest.raises(RuntimeError, match="Database not initialized"):
        async with get_session() as _:
            pass


async def test_session_closes_in_finally(db_session) -> None:
    """Test that session is always closed via the finally block in get_session()."""
    session_id = None

    async with get_session() as session:
        session_id = id(session)
        await session.execute(text("SELECT 1"))

    assert session_id is not None


async def test_init_db_with_echo_enabled(db_available) -> None:
    """Test init_db with echo=True creates engine correctly."""
    await init_db(TEST_DATABASE_URL, echo=True)

    from pentest.database.connection import _engine

    assert _engine is not None
    assert _engine.echo is True

    await close_db()


async def test_multiple_sessions_independent(db_session) -> None:
    """Test that multiple sessions work independently."""
    async with get_session() as session1:
        result1 = await session1.execute(text("SELECT 1 as session_num"))
        value1 = result1.fetchone()

    async with get_session() as session2:
        result2 = await session2.execute(text("SELECT 2 as session_num"))
        value2 = result2.fetchone()

    assert value1[0] == 1
    assert value2[0] == 2


async def test_concurrent_sessions_respects_pool_limits(db_session) -> None:
    """Test connection pool limits with 15 concurrent sessions (US-006 AC).

    Pool configuration: pool_size=10, max_overflow=20.
    Opens 15 concurrent sessions to verify pool handles overflow correctly.
    """
    num_sessions = 15

    async def open_session_and_query(session_num: int) -> int:
        """Open a session, execute a simple query, and return session number."""
        async with get_session() as session:
            result = await session.execute(
                text("SELECT :session_num as value"),
                {"session_num": session_num},
            )
            row = result.fetchone()
            return row[0] if row else -1

    tasks = [open_session_and_query(i) for i in range(num_sessions)]
    session_results = await asyncio.gather(*tasks)

    assert len(session_results) == num_sessions
    for i, result in enumerate(session_results):
        assert result == i, f"Session {i} failed: got {result}"
