# File: tests/integration/database/test_queries.py
import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from pentest.database.connection import get_session
from pentest.database.enums import (
    ContainerStatus,
    FlowStatus,
    MsglogResultFormat,
    MsglogType,
    SubtaskStatus,
    TaskStatus,
    TermlogType,
    ToolcallStatus,
)
from pentest.database.queries.containers import (
    CreateContainerParams,
    create_container,
    get_containers,
    get_flow_containers,
    update_container_image,
    update_container_status,
    update_container_status_local_id,
)
from pentest.database.queries.flows import (
    CreateFlowParams,
    create_flow,
    delete_flow,
    get_flow,
    get_flows,
    update_flow_status,
    update_flow_title,
)
from pentest.database.queries.msgchains import (
    CreateMsgchainParams,
    create_msgchain,
    update_msgchain_chain,
    update_msgchain_usage,
)
from pentest.database.queries.msglogs import (
    CreateMsglogParams,
    create_msglog,
    get_flow_msglogs,
    update_msglog_result,
)
from pentest.database.queries.subtasks import (
    CreateSubtaskParams,
    create_subtask,
    create_subtasks,
    delete_subtask,
    get_task_subtasks,
    update_subtask_result,
    update_subtask_status,
)
from pentest.database.queries.tasks import (
    CreateTaskParams,
    create_task,
    get_flow_tasks,
    update_task_result,
    update_task_status,
)
from pentest.database.queries.termlogs import (
    CreateTermlogParams,
    create_termlog,
    get_flow_termlogs,
)
from pentest.database.queries.toolcalls import (
    CreateToolcallParams,
    create_toolcall,
    update_toolcall_failed_result,
    update_toolcall_finished_result,
)


async def test_flow_crud_cycle(db_session):
    """Test full CRUD cycle for Flow entity."""
    async with get_session() as session:
        # Create
        params = CreateFlowParams(
            model="gpt-4",
            model_provider="openai",
            language="en",
            prompts={"system": "test"},
        )
        flow = await create_flow(session, params)
        assert flow.id is not None
        assert flow.title == "untitled"
        assert flow.status == FlowStatus.CREATED

        # Read
        fetched = await get_flow(session, flow.id)
        assert fetched.id == flow.id

        # Update status & updated_at check
        old_updated_at = flow.updated_at
        await asyncio.sleep(0.1)  # Ensure timestamp can change
        updated = await update_flow_status(session, flow.id, FlowStatus.RUNNING)
        assert updated.status == FlowStatus.RUNNING
        assert updated.updated_at >= old_updated_at

        # Update title
        updated = await update_flow_title(session, flow.id, "new title")
        assert updated.title == "new title"

        # List
        all_flows = await get_flows(session)
        assert len(all_flows) == 1
        assert all_flows[0].id == flow.id

        # Delete (soft)
        deleted = await delete_flow(session, flow.id)
        assert deleted.deleted_at is not None

        # Verify read/list excludes deleted
        all_flows_after = await get_flows(session)
        assert len(all_flows_after) == 0

        fetched_deleted = await get_flow(session, flow.id)
        assert fetched_deleted is None


async def test_task_crud_cycle(db_session):
    """Test full CRUD cycle for Task entity."""
    async with get_session() as session:
        # Setup: Create Flow
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        # Create
        params = CreateTaskParams(
            status=TaskStatus.CREATED,
            title="Task 1",
            input="do something",
            flow_id=flow.id,
        )
        task = await create_task(session, params)
        assert task.id is not None

        # Read (via flow)
        tasks = await get_flow_tasks(session, flow.id)
        assert len(tasks) == 1
        assert tasks[0].id == task.id

        # Update status
        updated = await update_task_status(session, task_id=task.id, status=TaskStatus.FINISHED)
        assert updated.status == TaskStatus.FINISHED

        # Update result
        updated = await update_task_result(session, task_id=task.id, result="done")
        assert updated.result == "done"


async def test_get_flow_tasks_ordering(db_session):
    """Test get_flow_tasks returns tasks ordered by created_at ASC."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        t1 = await create_task(
            session,
            CreateTaskParams(status=TaskStatus.CREATED, title="T1", input="i1", flow_id=flow.id),
        )
        await asyncio.sleep(0.1)
        t2 = await create_task(
            session,
            CreateTaskParams(status=TaskStatus.CREATED, title="T2", input="i2", flow_id=flow.id),
        )

        tasks = await get_flow_tasks(session, flow.id)
        assert len(tasks) == 2
        assert tasks[0].id == t1.id
        assert tasks[1].id == t2.id

        # Empty list for flow with no tasks
        flow2 = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )
        tasks2 = await get_flow_tasks(session, flow2.id)
        assert tasks2 == []


async def test_subtask_crud_cycle(db_session):
    """Test full CRUD cycle for Subtask entity."""
    async with get_session() as session:
        # Setup
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )
        task = await create_task(
            session,
            CreateTaskParams(status=TaskStatus.CREATED, title="T1", input="i1", flow_id=flow.id),
        )

        # Create
        subtask = await create_subtask(
            session,
            CreateSubtaskParams(
                status=SubtaskStatus.CREATED,
                title="S1",
                description="desc",
                task_id=task.id,
            ),
        )
        assert subtask.id is not None

        # Read
        subtasks = await get_task_subtasks(session, task.id)
        assert len(subtasks) == 1

        # Update
        updated = await update_subtask_status(session, subtask.id, SubtaskStatus.RUNNING)
        assert updated.status == SubtaskStatus.RUNNING

        updated = await update_subtask_result(session, subtask.id, "result")
        assert updated.result == "result"

        # Delete
        await delete_subtask(session, subtask.id)
        subtasks_after = await get_task_subtasks(session, task.id)
        assert len(subtasks_after) == 0


async def test_create_subtasks_bulk(db_session):
    """Test create_subtasks bulk creates subtasks."""
    async with get_session() as session:
        # Setup
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )
        task = await create_task(
            session,
            CreateTaskParams(status=TaskStatus.CREATED, title="T1", input="i1", flow_id=flow.id),
        )

        params_list = [
            CreateSubtaskParams(
                status=SubtaskStatus.CREATED,
                title=f"S{i}",
                description="d",
                task_id=task.id,
            )
            for i in range(5)
        ]
        created = await create_subtasks(session, params_list)
        assert len(created) == 5
        for s in created:
            assert s.id is not None

        subtasks = await get_task_subtasks(session, task.id)
        assert len(subtasks) == 5


async def test_container_crud_cycle(db_session):
    """Test full CRUD cycle for Container entity."""
    async with get_session() as session:
        # Setup
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        # Create
        container = await create_container(
            session,
            CreateContainerParams(
                image="alpine",
                flow_id=flow.id,
                local_id="cid1",
            ),
        )
        assert container.id is not None

        # Read
        all_containers = await get_containers(session)
        assert len(all_containers) == 1

        flow_containers = await get_flow_containers(session, flow.id)
        assert len(flow_containers) == 1

        # Update
        updated = await update_container_status(session, container.id, ContainerStatus.RUNNING)
        assert updated.status == ContainerStatus.RUNNING

        updated = await update_container_status_local_id(
            session, container.id, ContainerStatus.STOPPED, "cid_new"
        )
        assert updated.status == ContainerStatus.STOPPED
        assert updated.local_id == "cid_new"

        updated = await update_container_image(session, container.id, "ubuntu")
        assert updated.image == "ubuntu"


async def test_create_container_duplicate_local_id(db_session):
    """Test create_container with duplicate local_id raises IntegrityError."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        await create_container(
            session,
            CreateContainerParams(
                image="alpine",
                flow_id=flow.id,
                local_id="duplicate",
            ),
        )
        await session.commit()  # Commit first one

    async with get_session() as session:
        with pytest.raises(IntegrityError):
            async with get_session() as session:
                await create_container(
                    session,
                    CreateContainerParams(
                        image="ubuntu",
                        flow_id=flow.id,
                        local_id="duplicate",
                    ),
                )
                await session.commit()


async def test_toolcall_crud_cycle(db_session):
    """Test full CRUD cycle for Toolcall entity."""
    async with get_session() as session:
        # Setup
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        # Create
        toolcall = await create_toolcall(
            session,
            CreateToolcallParams(
                call_id="call1",
                name="test_tool",
                args={"a": 1},
                flow_id=flow.id,
            ),
        )
        assert toolcall.id is not None
        assert toolcall.status == ToolcallStatus.RECEIVED

        # Move to RUNNING before marking as FINISHED
        toolcall.status = ToolcallStatus.RUNNING
        await session.flush()

        # Update Finished
        updated = await update_toolcall_finished_result(
            session, toolcall.id, result="ok", duration_seconds=1.5
        )
        assert updated.status == ToolcallStatus.FINISHED
        assert updated.result == "ok"
        assert updated.duration_seconds == 1.5

        # Update Failed
        toolcall2 = await create_toolcall(
            session,
            CreateToolcallParams(
                call_id="call2",
                name="test_tool",
                flow_id=flow.id,
            ),
        )
        updated_fail = await update_toolcall_failed_result(
            session, toolcall2.id, result="err", duration_seconds=0.5
        )
        assert updated_fail.status == ToolcallStatus.FAILED
        assert updated_fail.result == "err"


async def test_msgchain_crud_cycle(db_session):
    """Test full CRUD cycle for Msgchain entity."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        # Create
        msgchain = await create_msgchain(
            session,
            CreateMsgchainParams(
                model="gpt-4",
                model_provider="openai",
                flow_id=flow.id,
            ),
        )
        assert msgchain.id is not None
        assert msgchain.usage_in == 0

        # Update chain
        new_chain = [{"role": "user", "content": "hi"}]
        updated = await update_msgchain_chain(session, msgchain.id, new_chain)
        assert updated.chain == new_chain

        # Update usage (accumulation)
        updated = await update_msgchain_usage(session, msgchain.id, 100, 50)
        assert updated.usage_in == 100
        assert updated.usage_out == 50

        updated = await update_msgchain_usage(session, msgchain.id, 200, 100)
        assert updated.usage_in == 300
        assert updated.usage_out == 150


async def test_termlog_crud_cycle(db_session):
    """Test full CRUD cycle for Termlog entity."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )
        container = await create_container(
            session, CreateContainerParams(image="a", flow_id=flow.id)
        )

        # Create
        log = await create_termlog(
            session,
            CreateTermlogParams(
                type=TermlogType.STDOUT,
                text="hello",
                container_id=container.id,
                flow_id=flow.id,
            ),
        )
        assert log.id is not None

        # Read
        logs = await get_flow_termlogs(session, flow.id)
        assert len(logs) == 1
        assert logs[0].text == "hello"


async def test_msglog_crud_cycle(db_session):
    """Test full CRUD cycle for Msglog entity."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )

        # Create
        log = await create_msglog(
            session,
            CreateMsglogParams(
                type=MsglogType.THOUGHTS,
                message="thinking",
                flow_id=flow.id,
            ),
        )
        assert log.id is not None

        # Update result
        updated = await update_msglog_result(session, log.id, "result", MsglogResultFormat.MARKDOWN)
        assert updated.result == "result"
        assert updated.result_format == MsglogResultFormat.MARKDOWN

        # Read
        logs = await get_flow_msglogs(session, flow.id)
        assert len(logs) == 1


async def test_transaction_rollback(db_session):
    """Test transaction rollback on error."""
    async with get_session() as session:
        flow = await create_flow(
            session,
            CreateFlowParams(model="gpt-4", model_provider="openai", language="en", prompts={}),
        )
        await session.commit()

    try:
        async with get_session() as session:
            # Create a task
            await create_task(
                session,
                CreateTaskParams(status=TaskStatus.CREATED, title="T1", input="i", flow_id=flow.id),
            )
            # Trigger an error by creating a container with duplicate local_id if it existed,
            # or just raise a manual exception after some work.
            # Actually, let's use a real DB error.
            await create_container(
                session,
                CreateContainerParams(image="a", flow_id=99999),  # Non-existent flow FK error
            )
            await session.commit()
    except Exception:
        pass

    # Verify task was NOT created because of rollback
    async with get_session() as session:
        tasks = await get_flow_tasks(session, flow.id)
        assert len(tasks) == 0
