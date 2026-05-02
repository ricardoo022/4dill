"""Integration tests for SQLAlchemy models (US-008).

Tests cover:
- Model creation and default values
- Relationships and cascade deletion
- Timestamps (created_at, updated_at)
- Soft deletes (deleted_at filtering)
- Index usage in queries
- Enum status fields
"""

import os
import re

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from pentest.database.connection import get_session
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
from pentest.database.models import (
    Container,
    Flow,
    Msgchain,
    Msglog,
    Subtask,
    Task,
    Termlog,
    Toolcall,
    VectorStore,
)

# Test database URL - uses DATABASE_URL from CI, or defaults for local development
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test",
    ),
)


pytestmark = pytest.mark.integration


async def test_flow_defaults(db_session) -> None:
    """Test Flow model creates with correct default values."""
    async with get_session() as session:
        # Create a Flow with only required fields
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "You are a penetration tester"},
        )
        session.add(flow)
        await session.flush()

        # Verify defaults were applied
        assert flow.status == FlowStatus.CREATED
        assert flow.title == "untitled"
        assert flow.functions == {}
        assert flow.trace_id is None
        assert flow.deleted_at is None
        assert flow.created_at is not None
        assert flow.updated_at is not None

        await session.commit()

        # Refetch and verify persistence
        result = await session.execute(select(Flow).where(Flow.id == flow.id))
        fetched_flow = result.scalar_one()
        assert fetched_flow.status == FlowStatus.CREATED
        assert fetched_flow.title == "untitled"
        assert fetched_flow.functions == {}


async def test_hierarchy_and_cascades(db_session) -> None:
    """Test Flow -> Task -> Subtask hierarchy and cascade deletion."""
    async with get_session() as session:
        # Create a complete hierarchy
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
            title="Test Flow",
        )
        session.add(flow)
        await session.flush()

        task = Task(
            flow_id=flow.id,
            status=TaskStatus.RUNNING,
            title="Test Task",
            input="scan target",
        )
        session.add(task)
        await session.flush()

        subtask = Subtask(
            task_id=task.id,
            status=SubtaskStatus.WAITING,
            title="Test Subtask",
            description="Perform reconnaissance",
        )
        session.add(subtask)
        await session.commit()

        # Verify hierarchy exists
        flow_id = flow.id
        task_id = task.id
        subtask_id = subtask.id

        # Verify we can fetch all layers
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        assert result.scalar_one() is not None

        result = await session.execute(select(Task).where(Task.id == task_id))
        assert result.scalar_one() is not None

        result = await session.execute(select(Subtask).where(Subtask.id == subtask_id))
        assert result.scalar_one() is not None

        # Delete the Flow and verify cascade
        await session.delete(flow)
        await session.commit()

        # Verify all descendants were cascade-deleted
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        assert result.scalar() is None

        result = await session.execute(select(Task).where(Task.id == task_id))
        assert result.scalar() is None

        result = await session.execute(select(Subtask).where(Subtask.id == subtask_id))
        assert result.scalar() is None


async def test_updated_at_trigger(db_session) -> None:
    """Test that updated_at is automatically updated when record changes."""
    async with get_session() as session:
        # Create a Flow
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.commit()

        flow_id = flow.id

        # Query to get the initial timestamps
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        flow_v1 = result.scalar_one()
        original_updated_at = flow_v1.updated_at
        original_created_at = flow_v1.created_at

        # Wait a tiny bit and modify
        import asyncio

        await asyncio.sleep(0.1)

        # Modify the Flow
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        flow_v2 = result.scalar_one()
        flow_v2.status = FlowStatus.RUNNING
        await session.commit()

        # Query again to verify updated_at changed
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        flow_v3 = result.scalar_one()

        assert flow_v3.updated_at is not None
        assert flow_v3.created_at == original_created_at
        assert flow_v3.updated_at >= original_updated_at


async def test_soft_delete_filter(db_session) -> None:
    """Test soft delete pattern with deleted_at field."""
    async with get_session() as session:
        # Create multiple flows
        flow1 = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
            title="Active",
        )
        flow2 = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
            title="To Delete",
        )
        session.add_all([flow1, flow2])
        await session.commit()

        flow1_id = flow1.id
        flow2_id = flow2.id

        # Soft-delete flow2 by refetching and updating
        result = await session.execute(select(Flow).where(Flow.id == flow2_id))
        flow2_to_delete = result.scalar_one()
        flow2_to_delete.deleted_at = func.now()
        await session.commit()

        # Query active flows only
        result = await session.execute(select(Flow).where(Flow.deleted_at.is_(None)))
        active_flows = result.scalars().all()

        # Should only return flow1
        assert len(active_flows) == 1
        assert active_flows[0].id == flow1_id

        # But direct query by ID should still find flow2
        result = await session.execute(select(Flow).where(Flow.id == flow2_id))
        assert result.scalar_one() is not None


async def test_status_index_query(db_session) -> None:
    """Test querying using status index."""
    async with get_session() as session:
        # Create flows with different statuses
        flow_created = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
            status=FlowStatus.CREATED,
        )
        flow_running = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
            status=FlowStatus.RUNNING,
        )
        session.add_all([flow_created, flow_running])
        await session.commit()

        # Query by status (uses index)
        result = await session.execute(select(Flow).where(Flow.status == FlowStatus.RUNNING))
        running_flows = result.scalars().all()

        assert len(running_flows) == 1
        assert running_flows[0].status == FlowStatus.RUNNING

        # Query all created
        result = await session.execute(select(Flow).where(Flow.status == FlowStatus.CREATED))
        created_flows = result.scalars().all()

        assert len(created_flows) == 1
        assert created_flows[0].status == FlowStatus.CREATED


async def test_task_relationships(db_session) -> None:
    """Test Flow.tasks relationship works at runtime under async SQLAlchemy."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        task1 = Task(
            flow_id=flow.id,
            status=TaskStatus.CREATED,
            title="Task 1",
            input="input 1",
        )
        task2 = Task(
            flow_id=flow.id,
            status=TaskStatus.CREATED,
            title="Task 2",
            input="input 2",
        )
        session.add_all([task1, task2])
        await session.commit()

        flow_id = flow.id

    async with get_session() as session:
        result = await session.execute(select(Flow).where(Flow.id == flow_id))
        fetched_flow = result.scalar_one()

        task_titles = {task.title for task in fetched_flow.tasks}
        assert task_titles == {"Task 1", "Task 2"}
        assert len(fetched_flow.tasks) == 2


async def test_subtask_relationships(db_session) -> None:
    """Test Subtask relationships to Task."""
    async with get_session() as session:
        # Create flow and task
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        flow_id = flow.id

        task = Task(
            flow_id=flow_id,
            status=TaskStatus.CREATED,
            title="Test Task",
            input="input",
        )
        session.add(task)
        await session.flush()

        task_id = task.id

        # Create multiple subtasks
        subtask1 = Subtask(
            task_id=task_id,
            status=SubtaskStatus.CREATED,
            title="Subtask 1",
            description="Description 1",
        )
        subtask2 = Subtask(
            task_id=task_id,
            status=SubtaskStatus.CREATED,
            title="Subtask 2",
            description="Description 2",
        )
        session.add_all([subtask1, subtask2])
        await session.commit()

        # Verify relationship by explicit query
        result = await session.execute(select(Subtask).where(Subtask.task_id == task_id))
        fetched_subtasks = result.scalars().all()
        assert len(fetched_subtasks) == 2

        subtask_titles = {st.title for st in fetched_subtasks}
        assert subtask_titles == {"Subtask 1", "Subtask 2"}


async def test_container_linked_to_flow(db_session) -> None:
    """Test Container persists and links correctly to a Flow."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        container = Container(
            flow_id=flow.id,
            image="kalilinux/kali-rolling",
            type=ContainerType.PRIMARY,
            status=ContainerStatus.RUNNING,
            local_id="docker-123",
        )
        session.add(container)
        await session.commit()

        result = await session.execute(select(Container).where(Container.id == container.id))
        fetched = result.scalar_one()

        assert fetched.flow_id == flow.id
        assert fetched.flow.id == flow.id


async def test_toolcall_nullable_task_and_subtask(db_session) -> None:
    """Test Toolcall accepts nullable task_id and subtask_id."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        toolcall = Toolcall(
            flow_id=flow.id,
            call_id="call-1",
            name="terminal",
            args={"command": "id"},
            status=ToolcallStatus.RECEIVED,
        )
        session.add(toolcall)
        await session.commit()

        result = await session.execute(select(Toolcall).where(Toolcall.id == toolcall.id))
        fetched = result.scalar_one()

        assert fetched.task_id is None
        assert fetched.subtask_id is None
        assert fetched.args == {"command": "id"}


async def test_msgchain_json_roundtrip(db_session) -> None:
    """Test Msgchain JSON chain is preserved."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        chain_payload = [
            {"role": "system", "content": "You are a pentester"},
            {"role": "user", "content": "Scan target"},
            {"role": "assistant", "content": "Calling terminal"},
        ]
        msgchain = Msgchain(
            flow_id=flow.id,
            type=MsgchainType.GENERATOR,
            model="claude-sonnet",
            model_provider="anthropic",
            chain=chain_payload,
        )
        session.add(msgchain)
        await session.commit()

        result = await session.execute(select(Msgchain).where(Msgchain.id == msgchain.id))
        fetched = result.scalar_one()

        assert fetched.chain == chain_payload


async def test_termlog_container_fk(db_session) -> None:
    """Test Termlog persists against the container FK."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        container = Container(flow_id=flow.id, image="kali", local_id="docker-logs")
        session.add(container)
        await session.flush()

        termlog = Termlog(
            container_id=container.id,
            flow_id=flow.id,
            type=TermlogType.STDOUT,
            text="nmap output",
        )
        session.add(termlog)
        await session.commit()

        result = await session.execute(select(Termlog).where(Termlog.id == termlog.id))
        fetched = result.scalar_one()

        assert fetched.container_id == container.id
        assert fetched.container.id == container.id


async def test_msglog_result_format_enum_roundtrip(db_session) -> None:
    """Test Msglog result_format enum serializes correctly."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        msglog = Msglog(
            flow_id=flow.id,
            type=MsglogType.REPORT,
            message="scan finished",
            result="report body",
            result_format=MsglogResultFormat.MARKDOWN,
        )
        session.add(msglog)
        await session.commit()

        result = await session.execute(select(Msglog).where(Msglog.id == msglog.id))
        fetched = result.scalar_one()

        assert fetched.result_format == MsglogResultFormat.MARKDOWN


async def test_flow_cascades_supporting_models(db_session) -> None:
    """Test Flow cascade deletes supporting runtime models."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        task = Task(flow_id=flow.id, status=TaskStatus.CREATED, title="Task", input="input")
        session.add(task)
        await session.flush()

        subtask = Subtask(
            task_id=task.id,
            status=SubtaskStatus.CREATED,
            title="Subtask",
            description="desc",
        )
        session.add(subtask)
        await session.flush()

        container = Container(flow_id=flow.id, image="kali", local_id="docker-cascade")
        toolcall = Toolcall(
            flow_id=flow.id,
            task_id=task.id,
            subtask_id=subtask.id,
            call_id="call-cascade",
            name="terminal",
            args={"command": "id"},
        )
        msgchain = Msgchain(
            flow_id=flow.id,
            task_id=task.id,
            subtask_id=subtask.id,
            model="claude",
            model_provider="anthropic",
            chain=[{"role": "user", "content": "test"}],
        )
        msglog = Msglog(
            flow_id=flow.id,
            task_id=task.id,
            subtask_id=subtask.id,
            type=MsglogType.TERMINAL,
            message="executed terminal",
        )
        session.add_all([container, toolcall, msgchain, msglog])
        await session.commit()

        flow_id = flow.id
        container_id = container.id

        await session.delete(flow)
        await session.commit()

        assert (
            await session.execute(select(Container).where(Container.id == container_id))
        ).scalar() is None
        assert (
            await session.execute(select(Toolcall).where(Toolcall.flow_id == flow_id))
        ).scalars().all() == []
        assert (
            await session.execute(select(Msgchain).where(Msgchain.flow_id == flow_id))
        ).scalars().all() == []
        assert (
            await session.execute(select(Msglog).where(Msglog.flow_id == flow_id))
        ).scalars().all() == []


async def test_container_cascades_termlogs(db_session) -> None:
    """Test deleting a Container cascade deletes its Termlogs."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        container = Container(flow_id=flow.id, image="kali", local_id="docker-term-cascade")
        session.add(container)
        await session.flush()

        termlog = Termlog(
            container_id=container.id,
            flow_id=flow.id,
            type=TermlogType.STDERR,
            text="permission denied",
        )
        session.add(termlog)
        await session.commit()

        termlog_id = termlog.id
        await session.delete(container)
        await session.commit()

        result = await session.execute(select(Termlog).where(Termlog.id == termlog_id))
        assert result.scalar_one_or_none() is None


async def test_toolcall_name_index_query(db_session) -> None:
    """Test Toolcall name-based query pattern required by US-009."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        session.add_all(
            [
                Toolcall(flow_id=flow.id, call_id="call-1", name="terminal", args={}),
                Toolcall(flow_id=flow.id, call_id="call-2", name="browser", args={}),
            ]
        )
        await session.commit()

        result = await session.execute(select(Toolcall).where(Toolcall.name == "terminal"))
        fetched = result.scalars().all()

        assert len(fetched) == 1
        assert fetched[0].name == "terminal"


async def test_container_local_id_unique_constraint(db_session) -> None:
    """Test Container.local_id uniqueness is enforced by the database."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        session.add(Container(flow_id=flow.id, image="kali", local_id="duplicate-id"))
        await session.commit()

    async with get_session() as session:
        flow = (
            (await session.execute(select(Flow).where(Flow.title == "untitled"))).scalars().first()
        )
        session.add(Container(flow_id=flow.id, image="kali", local_id="duplicate-id"))

        with pytest.raises(IntegrityError):
            await session.commit()

        await session.rollback()


async def test_msgchain_usage_fields_can_be_updated(db_session) -> None:
    """Test Msgchain usage counters persist updates correctly."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        msgchain = Msgchain(
            flow_id=flow.id,
            model="claude",
            model_provider="anthropic",
            chain=[],
        )
        session.add(msgchain)
        await session.commit()

        result = await session.execute(select(Msgchain).where(Msgchain.id == msgchain.id))
        fetched = result.scalar_one()
        fetched.usage_in += 100
        fetched.usage_out += 50
        await session.commit()

        result = await session.execute(select(Msgchain).where(Msgchain.id == msgchain.id))
        updated = result.scalar_one()

        assert updated.usage_in == 100
        assert updated.usage_out == 50


async def test_supporting_models_required_defaults(db_session) -> None:
    """Test US-009 required defaults for supporting runtime models are applied."""
    async with get_session() as session:
        flow = Flow(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        session.add(flow)
        await session.flush()

        task = Task(flow_id=flow.id, status=TaskStatus.CREATED, title="Task", input="input")
        session.add(task)
        await session.flush()

        subtask = Subtask(
            task_id=task.id,
            status=SubtaskStatus.CREATED,
            title="Subtask",
            description="desc",
        )
        session.add(subtask)
        await session.flush()

        container = Container(flow_id=flow.id, image="kalilinux/kali-rolling")
        toolcall = Toolcall(flow_id=flow.id, call_id="defaults-call", name="terminal", args={})
        msgchain = Msgchain(flow_id=flow.id, model="claude", model_provider="anthropic", chain=[])
        msglog = Msglog(flow_id=flow.id, type=MsglogType.ANSWER, message="default formatting")
        termlog = Termlog(
            container=container,
            flow_id=flow.id,
            task_id=task.id,
            subtask_id=subtask.id,
            type=TermlogType.STDIN,
            text="whoami",
        )

        session.add_all([container, toolcall, msgchain, msglog, termlog])
        await session.commit()

        assert container.type == ContainerType.PRIMARY
        assert container.status == ContainerStatus.STARTING
        assert re.fullmatch(r"[0-9a-f]{32}", container.name) is not None

        assert toolcall.status == ToolcallStatus.RECEIVED
        assert toolcall.result == ""
        assert toolcall.duration_seconds == 0.0

        assert msgchain.type == MsgchainType.PRIMARY_AGENT
        assert msgchain.usage_in == 0
        assert msgchain.usage_out == 0
        assert msgchain.usage_cache_in == 0
        assert msgchain.usage_cache_out == 0
        assert msgchain.usage_cost_in == 0.0
        assert msgchain.usage_cost_out == 0.0
        assert msgchain.duration_seconds == 0.0

        assert msglog.result == ""
        assert msglog.result_format == MsglogResultFormat.PLAIN


async def test_vector_extension_exists(db_session) -> None:
    """US-010: pgvector extension should exist after setup/helper."""
    async with get_session() as session:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar_one() == "vector"


async def test_vector_store_create_and_similarity_query(db_session) -> None:
    """US-010: insert 1536-d vectors and query nearest neighbors."""
    async with get_session() as session:
        base = [0.0] * 1536
        near = [0.0] * 1536
        far = [0.0] * 1536
        base[0] = 1.0
        near[0] = 0.99
        near[1] = 0.01
        far[10] = 1.0

        session.add_all(
            [
                VectorStore(
                    content="base",
                    metadata_={"flow_id": 1, "task_id": 10, "doc_type": "guide"},
                    embedding=base,
                ),
                VectorStore(
                    content="near",
                    metadata_={"flow_id": 1, "task_id": 11, "doc_type": "answer"},
                    embedding=near,
                ),
                VectorStore(
                    content="far",
                    metadata_={"flow_id": 2, "task_id": 12, "doc_type": "code"},
                    embedding=far,
                ),
            ]
        )
        await session.flush()

    async with get_session() as session:
        query_vector = [0.0] * 1536
        query_vector[0] = 1.0

        result = await session.execute(
            select(VectorStore)
            .order_by(VectorStore.embedding.cosine_distance(query_vector))
            .limit(3)
        )
        nearest = result.scalars().all()

        assert nearest[0].content == "base"

        # ivfflat is approximate and can return fewer candidates depending on probes.
        # Validate relative semantic proximity directly to keep this deterministic.
        near_distance_result = await session.execute(
            select(VectorStore.embedding.cosine_distance(query_vector)).where(
                VectorStore.content == "near"
            )
        )
        far_distance_result = await session.execute(
            select(VectorStore.embedding.cosine_distance(query_vector)).where(
                VectorStore.content == "far"
            )
        )

        near_distance = near_distance_result.scalar_one()
        far_distance = far_distance_result.scalar_one()
        assert near_distance < far_distance


async def test_vector_store_metadata_filtering(db_session) -> None:
    """US-010: metadata filters by flow_id/task_id/doc_type should work."""
    async with get_session() as session:
        vector = [0.0] * 1536
        vector[7] = 1.0

        session.add_all(
            [
                VectorStore(
                    content="doc-flow-1-guide",
                    metadata_={"flow_id": 1, "task_id": 101, "doc_type": "guide"},
                    embedding=vector,
                ),
                VectorStore(
                    content="doc-flow-1-answer",
                    metadata_={"flow_id": 1, "task_id": 102, "doc_type": "answer"},
                    embedding=vector,
                ),
                VectorStore(
                    content="doc-flow-2-code",
                    metadata_={"flow_id": 2, "task_id": 201, "doc_type": "code"},
                    embedding=vector,
                ),
            ]
        )
        await session.flush()

        by_flow = await session.execute(
            select(VectorStore).where(text("metadata_->>'flow_id' = '1'"))
        )
        assert {doc.content for doc in by_flow.scalars().all()} == {
            "doc-flow-1-guide",
            "doc-flow-1-answer",
        }

        by_task = await session.execute(
            select(VectorStore).where(text("metadata_->>'task_id' = '201'"))
        )
        assert [doc.content for doc in by_task.scalars().all()] == ["doc-flow-2-code"]

        by_doc_type = await session.execute(
            select(VectorStore).where(text("metadata_->>'doc_type' = 'guide'"))
        )
        assert [doc.content for doc in by_doc_type.scalars().all()] == ["doc-flow-1-guide"]


async def test_vector_store_insert_many_and_ordered_similarity(db_session) -> None:
    """US-010: similarity query over 100 rows should return deterministic nearest first."""
    async with get_session() as session:
        rows: list[VectorStore] = []
        for i in range(100):
            embedding = [0.0] * 1536
            embedding[0] = 1.0 if i == 42 else 0.001
            embedding[1] = float(i) / 1000.0
            rows.append(
                VectorStore(
                    content=f"doc-{i}",
                    metadata_={"flow_id": i % 3, "task_id": i, "doc_type": "guide"},
                    embedding=embedding,
                )
            )

        session.add_all(rows)
        await session.flush()

    async with get_session() as session:
        query_vector = [0.0] * 1536
        query_vector[0] = 1.0
        query_vector[1] = 0.042

        result = await session.execute(
            select(VectorStore)
            .order_by(VectorStore.embedding.cosine_distance(query_vector))
            .limit(1)
        )
        nearest = result.scalar_one()
        assert nearest.content == "doc-42"


async def test_vector_store_wrong_dimension_rejected(db_session) -> None:
    """US-010: vectors with wrong dimensions should fail."""
    async with get_session() as session:
        bad_embedding = [0.0] * 768
        row = VectorStore(content="bad", metadata_={"flow_id": 1}, embedding=bad_embedding)
        session.add(row)

        with pytest.raises(StatementError, match="expected 1536 dimensions"):
            await session.flush()
        await session.rollback()
