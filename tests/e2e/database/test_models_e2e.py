"""US-008 E2E tests for core SQLAlchemy models against a real database service."""

from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import StatementError

from pentest.database.connection import close_db, get_session, init_db
from pentest.database.enums import (
    ContainerStatus,
    ContainerType,
    FlowStatus,
    MsgchainType,
    MsglogResultFormat,
    MsglogType,
    SubtaskStatus,
    TaskStatus,
    TermlogType,
    ToolcallStatus,
)
from pentest.database.exceptions import DatabaseConnectionError
from pentest.database.models import (
    Base,
    Container,
    Flow,
    Msgchain,
    Msglog,
    Subtask,
    Task,
    Termlog,
    Toolcall,
    VectorStore,
    create_vector_extension,
)

pytestmark = pytest.mark.e2e

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
)


async def _db_is_reachable() -> bool:
    """Return True when the configured database can be reached."""
    try:
        await init_db(TEST_DATABASE_URL, echo=False)
        await close_db()
        return True
    except (DatabaseConnectionError, Exception):
        return False


@pytest.fixture()
async def e2e_database_available():
    """Skip when the real database service is not available."""
    if not await _db_is_reachable():
        pytest.skip("Real database service not available for E2E test")


@pytest.fixture()
async def db_schema(e2e_database_available):
    """Recreate the US-009 schema in the real database for E2E validation."""
    await init_db(TEST_DATABASE_URL, echo=False)

    async with get_session() as session:
        conn = await session.connection()
        await conn.execute(text("DROP TABLE IF EXISTS vector_store CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS termlogs CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS msglogs CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS msgchains CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS toolcalls CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS containers CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS subtasks CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS tasks CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS flows CASCADE"))

        await conn.execute(text("DROP TYPE IF EXISTS msglog_result_format CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS msglog_type CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS termlog_type CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS msgchain_type CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS toolcall_status CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS container_status CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS container_type CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS flow_status CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS task_status CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS subtask_status CASCADE"))

        await conn.execute(
            text(
                """
                CREATE TYPE container_type AS ENUM (
                    'primary', 'secondary'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE container_status AS ENUM (
                    'starting', 'running', 'stopped', 'deleted', 'failed'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE toolcall_status AS ENUM (
                    'received', 'running', 'finished', 'failed'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE msgchain_type AS ENUM (
                    'primary_agent', 'reporter', 'generator', 'refiner', 'reflector',
                    'enricher', 'adviser', 'coder', 'memorist', 'searcher', 'installer',
                    'pentester', 'summarizer', 'tool_call_fixer'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE termlog_type AS ENUM (
                    'stdin', 'stdout', 'stderr'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE msglog_type AS ENUM (
                    'thoughts', 'browser', 'terminal', 'file', 'search',
                    'advice', 'input', 'done', 'answer', 'report'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE msglog_result_format AS ENUM (
                    'terminal', 'plain', 'markdown'
                )
                """
            )
        )

        await conn.execute(
            text(
                """
                CREATE TYPE flow_status AS ENUM (
                    'created', 'running', 'waiting', 'finished', 'failed'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE task_status AS ENUM (
                    'created', 'running', 'waiting', 'finished', 'failed'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TYPE subtask_status AS ENUM (
                    'created', 'running', 'waiting', 'finished', 'failed'
                )
                """
            )
        )

        await create_vector_extension(conn)
        await conn.run_sync(Base.metadata.create_all)

    await close_db()
    yield
    await close_db()


@pytest.fixture()
async def db_session(db_schema):
    """Initialize the DB for one E2E test and clean up data afterward."""
    await init_db(TEST_DATABASE_URL, echo=False)
    yield

    async with get_session() as session:
        await session.execute(text("DELETE FROM vector_store"))
        await session.execute(text("DELETE FROM termlogs"))
        await session.execute(text("DELETE FROM msglogs"))
        await session.execute(text("DELETE FROM msgchains"))
        await session.execute(text("DELETE FROM toolcalls"))
        await session.execute(text("DELETE FROM containers"))
        await session.execute(text("DELETE FROM subtasks"))
        await session.execute(text("DELETE FROM tasks"))
        await session.execute(text("DELETE FROM flows"))

    await close_db()


async def test_us008_models_end_to_end_real_db(db_session) -> None:
    """E2E: persist and reload the runtime hierarchy including US-009 models."""
    async with get_session() as session:
        flow = Flow(
            model="claude-3-7-sonnet",
            model_provider="anthropic",
            language="en",
            prompts={"system": "Run pentest workflow"},
            title="E2E Flow",
            status=FlowStatus.RUNNING,
        )
        session.add(flow)
        await session.flush()

        task1 = Task(
            flow_id=flow.id,
            status=TaskStatus.CREATED,
            title="Recon",
            input="Collect target metadata",
        )
        task2 = Task(
            flow_id=flow.id,
            status=TaskStatus.WAITING,
            title="Exploit",
            input="Prepare exploit path",
        )
        session.add_all([task1, task2])
        await session.flush()

        subtask = Subtask(
            task_id=task1.id,
            status=SubtaskStatus.RUNNING,
            title="DNS Lookup",
            description="Resolve target records",
            context="public target",
        )
        session.add(subtask)
        await session.flush()

        container = Container(
            flow_id=flow.id,
            image="kalilinux/kali-rolling",
            type=ContainerType.PRIMARY,
            local_id="e2e-container-id",
        )
        session.add(container)
        await session.flush()

        session.add_all(
            [
                Toolcall(
                    flow_id=flow.id,
                    task_id=task1.id,
                    subtask_id=subtask.id,
                    call_id="e2e-call-id",
                    name="terminal",
                    args={"command": "id"},
                ),
                Msgchain(
                    flow_id=flow.id,
                    task_id=task1.id,
                    subtask_id=subtask.id,
                    type=MsgchainType.GENERATOR,
                    model="claude-3-7-sonnet",
                    model_provider="anthropic",
                    chain=[{"role": "assistant", "content": "Calling terminal"}],
                ),
                Termlog(
                    container_id=container.id,
                    flow_id=flow.id,
                    task_id=task1.id,
                    subtask_id=subtask.id,
                    type=TermlogType.STDOUT,
                    text="uid=0(root)",
                ),
                Msglog(
                    flow_id=flow.id,
                    task_id=task1.id,
                    subtask_id=subtask.id,
                    type=MsglogType.REPORT,
                    message="Scan complete",
                    result="## Report",
                    result_format=MsglogResultFormat.MARKDOWN,
                ),
            ]
        )

        flow_id = flow.id
        task1_id = task1.id
        container_id = container.id

    async with get_session() as session:
        flow_result = await session.execute(select(Flow).where(Flow.id == flow_id))
        fetched_flow = flow_result.scalar_one()

        assert fetched_flow.title == "E2E Flow"
        assert fetched_flow.status == FlowStatus.RUNNING
        assert {task.title for task in fetched_flow.tasks} == {"Recon", "Exploit"}

        task_result = await session.execute(select(Task).where(Task.id == task1_id))
        fetched_task = task_result.scalar_one()

        assert fetched_task.flow.id == flow_id
        assert len(fetched_task.subtasks) == 1
        assert fetched_task.subtasks[0].title == "DNS Lookup"

        container_result = await session.execute(
            select(Container).where(Container.id == container_id)
        )
        fetched_container = container_result.scalar_one()
        assert fetched_container.flow.id == flow_id
        assert len(fetched_container.termlogs) == 1

        toolcall_result = await session.execute(select(Toolcall).where(Toolcall.flow_id == flow_id))
        assert toolcall_result.scalars().one().name == "terminal"

        msgchain_result = await session.execute(select(Msgchain).where(Msgchain.flow_id == flow_id))
        assert msgchain_result.scalars().one().type == MsgchainType.GENERATOR

        msglog_result = await session.execute(select(Msglog).where(Msglog.flow_id == flow_id))
        assert msglog_result.scalars().one().result_format == MsglogResultFormat.MARKDOWN

        await session.delete(fetched_flow)

    async with get_session() as session:
        flow_result = await session.execute(select(Flow).where(Flow.id == flow_id))
        task_result = await session.execute(select(Task).where(Task.flow_id == flow_id))
        subtask_result = await session.execute(select(Subtask).join(Task))
        container_result = await session.execute(
            select(Container).where(Container.flow_id == flow_id)
        )
        toolcall_result = await session.execute(select(Toolcall).where(Toolcall.flow_id == flow_id))
        msgchain_result = await session.execute(select(Msgchain).where(Msgchain.flow_id == flow_id))
        msglog_result = await session.execute(select(Msglog).where(Msglog.flow_id == flow_id))
        termlog_result = await session.execute(select(Termlog).where(Termlog.flow_id == flow_id))

        assert flow_result.scalar_one_or_none() is None
        assert task_result.scalars().all() == []
        assert subtask_result.scalars().all() == []
        assert container_result.scalars().all() == []
        assert toolcall_result.scalars().all() == []
        assert msgchain_result.scalars().all() == []
        assert msglog_result.scalars().all() == []
        assert termlog_result.scalars().all() == []


async def test_us009_models_defaults_end_to_end_real_db(db_session) -> None:
    """E2E: required US-009 defaults persist correctly in a real PostgreSQL database."""
    async with get_session() as session:
        flow = Flow(
            model="claude-3-7-sonnet",
            model_provider="anthropic",
            language="en",
            prompts={"system": "Run pentest workflow"},
        )
        session.add(flow)
        await session.flush()

        task = Task(
            flow_id=flow.id,
            status=TaskStatus.CREATED,
            title="Defaults Task",
            input="Collect target metadata",
        )
        session.add(task)
        await session.flush()

        subtask = Subtask(
            task_id=task.id,
            status=SubtaskStatus.CREATED,
            title="Defaults Subtask",
            description="Exercise supporting model defaults",
        )
        session.add(subtask)
        await session.flush()

        container = Container(flow_id=flow.id, image="kalilinux/kali-rolling")
        toolcall = Toolcall(flow_id=flow.id, call_id="defaults-e2e", name="terminal", args={})
        msgchain = Msgchain(
            flow_id=flow.id,
            model="claude-3-7-sonnet",
            model_provider="anthropic",
            chain=[],
        )
        msglog = Msglog(
            flow_id=flow.id,
            type=MsglogType.ANSWER,
            message="Default formatting result",
        )
        termlog = Termlog(
            container=container,
            flow_id=flow.id,
            task_id=task.id,
            subtask_id=subtask.id,
            type=TermlogType.STDIN,
            text="whoami",
        )
        session.add_all([container, toolcall, msgchain, msglog, termlog])

    async with get_session() as session:
        container_result = await session.execute(
            select(Container).where(Container.flow_id == flow.id)
        )
        fetched_container = container_result.scalar_one()
        assert fetched_container.type == ContainerType.PRIMARY
        assert fetched_container.status == ContainerStatus.STARTING
        assert re.fullmatch(r"[0-9a-f]{32}", fetched_container.name) is not None

        toolcall_result = await session.execute(select(Toolcall).where(Toolcall.flow_id == flow.id))
        fetched_toolcall = toolcall_result.scalar_one()
        assert fetched_toolcall.status == ToolcallStatus.RECEIVED
        assert fetched_toolcall.result == ""
        assert fetched_toolcall.duration_seconds == 0.0

        msgchain_result = await session.execute(select(Msgchain).where(Msgchain.flow_id == flow.id))
        fetched_msgchain = msgchain_result.scalar_one()
        assert fetched_msgchain.type == MsgchainType.PRIMARY_AGENT
        assert fetched_msgchain.usage_in == 0
        assert fetched_msgchain.usage_out == 0
        assert fetched_msgchain.usage_cache_in == 0
        assert fetched_msgchain.usage_cache_out == 0
        assert fetched_msgchain.usage_cost_in == 0.0
        assert fetched_msgchain.usage_cost_out == 0.0
        assert fetched_msgchain.duration_seconds == 0.0

        msglog_result = await session.execute(select(Msglog).where(Msglog.flow_id == flow.id))
        fetched_msglog = msglog_result.scalar_one()
        assert fetched_msglog.result == ""
        assert fetched_msglog.result_format == MsglogResultFormat.PLAIN


async def test_us009_index_definitions_exist_in_real_db(db_session) -> None:
    """E2E: expected US-009 indexes exist in PostgreSQL system catalogs."""
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'containers',
                    'toolcalls',
                    'msgchains',
                    'termlogs',
                    'msglogs',
                    'vector_store'
                  )
                """
            )
        )
        index_names = {row.indexname for row in result}

        assert {
            "ix_containers_type",
            "ix_containers_name",
            "ix_containers_status",
            "ix_containers_flow_id",
            "ix_toolcalls_call_id",
            "ix_toolcalls_status",
            "ix_toolcalls_name",
            "ix_toolcalls_flow_id",
            "ix_toolcalls_task_id",
            "ix_toolcalls_subtask_id",
            "ix_toolcalls_created_at",
            "ix_toolcalls_updated_at",
            "ix_toolcalls_flow_id_status",
            "ix_toolcalls_name_status",
            "ix_toolcalls_name_flow_id",
            "ix_toolcalls_status_updated_at",
            "ix_msgchains_type",
            "ix_msgchains_flow_id",
            "ix_msgchains_task_id",
            "ix_msgchains_subtask_id",
            "ix_msgchains_created_at",
            "ix_msgchains_model_provider",
            "ix_msgchains_model",
            "ix_msgchains_type_flow_id",
            "ix_msgchains_created_at_flow_id",
            "ix_msgchains_type_created_at",
            "ix_msgchains_type_task_id_subtask_id",
            "ix_termlogs_type",
            "ix_termlogs_container_id",
            "ix_termlogs_flow_id",
            "ix_termlogs_task_id",
            "ix_termlogs_subtask_id",
            "ix_msglogs_type",
            "ix_msglogs_flow_id",
            "ix_msglogs_task_id",
            "ix_msglogs_subtask_id",
            "ix_msglogs_result_format",
            "ix_vector_store_embedding_ivfflat",
            "ix_vector_store_metadata_flow_id",
            "ix_vector_store_metadata_task_id",
            "ix_vector_store_metadata_doc_type",
        }.issubset(index_names)


async def test_us010_vector_store_similarity_and_metadata_filters_e2e(db_session) -> None:
    """E2E: vector similarity and metadata filters work in real PostgreSQL+pgvector."""
    async with get_session() as session:
        query = [0.0] * 1536
        query[0] = 1.0

        base = [0.0] * 1536
        near = [0.0] * 1536
        far = [0.0] * 1536
        base[0] = 1.0
        near[0] = 0.95
        near[2] = 0.05
        far[20] = 1.0

        session.add_all(
            [
                VectorStore(
                    content="e2e-base",
                    metadata_={"flow_id": 11, "task_id": 101, "doc_type": "guide"},
                    embedding=base,
                ),
                VectorStore(
                    content="e2e-near",
                    metadata_={"flow_id": 11, "task_id": 102, "doc_type": "answer"},
                    embedding=near,
                ),
                VectorStore(
                    content="e2e-far",
                    metadata_={"flow_id": 12, "task_id": 103, "doc_type": "code"},
                    embedding=far,
                ),
            ]
        )
        await session.flush()

    async with get_session() as session:
        query = [0.0] * 1536
        query[0] = 1.0

        nearest_result = await session.execute(
            select(VectorStore).order_by(VectorStore.embedding.cosine_distance(query)).limit(3)
        )
        nearest_docs = [row.content for row in nearest_result.scalars().all()]
        assert nearest_docs[0] == "e2e-base"

        filtered_result = await session.execute(
            select(VectorStore).where(text("metadata_->>'flow_id' = '11'"))
        )
        assert {row.content for row in filtered_result.scalars().all()} == {
            "e2e-base",
            "e2e-near",
        }


async def test_us010_vector_store_insert_search_delete_e2e(db_session) -> None:
    """E2E: insert vector row, retrieve by similarity, delete it, and verify removal."""
    embedding = [0.0] * 1536
    embedding[0] = 1.0

    async with get_session() as session:
        row = VectorStore(
            content="e2e-proof-openvpn-cve-2024-12345",
            metadata_={"flow_id": 77, "task_id": 701, "doc_type": "answer"},
            embedding=embedding,
        )
        session.add(row)
        await session.flush()
        row_id = row.id

    async with get_session() as session:
        result = await session.execute(
            select(VectorStore)
            .where(text("metadata_->>'flow_id' = '77'"))
            .order_by(VectorStore.embedding.cosine_distance(embedding))
            .limit(1)
        )
        fetched = result.scalar_one()
        assert fetched.id == row_id
        assert "openvpn" in fetched.content.lower()

    async with get_session() as session:
        delete_result = await session.execute(delete(VectorStore).where(VectorStore.id == row_id))
        assert delete_result.rowcount == 1

    async with get_session() as session:
        result = await session.execute(select(VectorStore).where(VectorStore.id == row_id))
        assert result.scalar_one_or_none() is None


async def test_us010_vector_extension_idempotent_e2e(db_session) -> None:
    """E2E: create_vector_extension can be called repeatedly without errors."""
    async with get_session() as session:
        conn = await session.connection()
        await create_vector_extension(conn)
        await create_vector_extension(conn)

        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar_one() == "vector"


async def test_us010_vector_index_uses_ivfflat_cosine_ops_e2e(db_session) -> None:
    """E2E: embedding index uses ivfflat with cosine operator class."""
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'vector_store'
                  AND indexname = 'ix_vector_store_embedding_ivfflat'
                """
            )
        )
        indexdef = result.scalar_one()
        assert "USING ivfflat" in indexdef
        assert "vector_cosine_ops" in indexdef


async def test_us010_vector_store_metadata_task_and_doc_type_filters_e2e(db_session) -> None:
    """E2E: metadata filters for task_id and doc_type return exact matching rows."""
    embedding = [0.0] * 1536
    embedding[5] = 1.0

    async with get_session() as session:
        session.add_all(
            [
                VectorStore(
                    content="e2e-task-900-guide",
                    metadata_={"flow_id": 90, "task_id": 900, "doc_type": "guide"},
                    embedding=embedding,
                ),
                VectorStore(
                    content="e2e-task-901-answer",
                    metadata_={"flow_id": 90, "task_id": 901, "doc_type": "answer"},
                    embedding=embedding,
                ),
                VectorStore(
                    content="e2e-task-900-code",
                    metadata_={"flow_id": 91, "task_id": 900, "doc_type": "code"},
                    embedding=embedding,
                ),
            ]
        )
        await session.flush()

    async with get_session() as session:
        task_result = await session.execute(
            select(VectorStore).where(text("metadata_->>'task_id' = '900'"))
        )
        assert {row.content for row in task_result.scalars().all()} == {
            "e2e-task-900-guide",
            "e2e-task-900-code",
        }

        doc_type_result = await session.execute(
            select(VectorStore).where(text("metadata_->>'doc_type' = 'answer'"))
        )
        assert [row.content for row in doc_type_result.scalars().all()] == ["e2e-task-901-answer"]


async def test_us010_vector_store_wrong_dimension_rejected_e2e(db_session) -> None:
    """E2E: inserting vector with wrong dimension is rejected by pgvector type."""
    async with get_session() as session:
        invalid = VectorStore(
            content="e2e-invalid-dim",
            metadata_={"flow_id": 404, "task_id": 1, "doc_type": "answer"},
            embedding=[0.0] * 768,
        )
        session.add(invalid)

        with pytest.raises(StatementError, match="expected 1536 dimensions"):
            await session.flush()

        await session.rollback()
