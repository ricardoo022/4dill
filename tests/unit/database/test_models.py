"""Unit tests for SQLAlchemy models (US-008).

Tests cover model structure without database connection:
- Model class attributes and annotations
- Default column values
- Relationship definitions
- Index configuration
- Foreign key constraints
"""

import re
from typing import cast

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index, inspect
from sqlalchemy.orm import RelationshipProperty

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


class TestFlowModel:
    """Unit tests for Flow model structure."""

    def test_flow_tablename(self):
        """Flow model should have correct table name."""
        assert Flow.__tablename__ == "flows"

    def test_flow_has_all_columns(self):
        """Flow should have all required columns."""
        mapper = inspect(Flow)
        column_names = {col.key for col in mapper.columns}

        required_columns = {
            "id",
            "status",
            "title",
            "model",
            "model_provider",
            "language",
            "functions",
            "prompts",
            "tool_call_id_template",
            "trace_id",
            "created_at",
            "updated_at",
            "deleted_at",
        }

        assert required_columns.issubset(column_names)

    def test_flow_has_tasks_relationship(self):
        """Flow should have tasks relationship."""
        mapper = inspect(Flow)
        relationships = {rel.key: rel for rel in mapper.relationships}

        assert "tasks" in relationships
        assert isinstance(relationships["tasks"], RelationshipProperty)

    def test_flow_status_default_value(self):
        """Flow status should default to CREATED."""
        mapper = inspect(Flow)
        status_col = mapper.columns["status"]
        # Default is via server_default (database side)
        assert status_col.server_default is not None

    def test_flow_title_default_value(self):
        """Flow title should default to 'untitled'."""
        mapper = inspect(Flow)
        title_col = mapper.columns["title"]
        assert title_col.default is not None

    def test_flow_functions_default_value(self):
        """Flow functions should default to dict."""
        mapper = inspect(Flow)
        functions_col = mapper.columns["functions"]
        assert functions_col.default is not None

    def test_flow_has_indexes(self):
        """Flow should have indexes on status and title."""
        # Access indexes via table_args which is a tuple of Index objects
        table_args = Flow.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_flows_status" in index_names
            assert "ix_flows_title" in index_names

    def test_flow_timestamps_nullable_false(self):
        """created_at and updated_at should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["created_at"].nullable is False
        assert mapper.columns["updated_at"].nullable is False

    def test_flow_deleted_at_nullable(self):
        """deleted_at should be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["deleted_at"].nullable is True

    def test_flow_trace_id_nullable(self):
        """trace_id should be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["trace_id"].nullable is True


class TestTaskModel:
    """Unit tests for Task model structure."""

    def test_task_tablename(self):
        """Task model should have correct table name."""
        assert Task.__tablename__ == "tasks"

    def test_task_has_all_columns(self):
        """Task should have all required columns."""
        mapper = inspect(Task)
        column_names = {col.key for col in mapper.columns}

        required_columns = {
            "id",
            "status",
            "title",
            "input",
            "result",
            "flow_id",
            "created_at",
            "updated_at",
        }

        assert required_columns.issubset(column_names)

    def test_task_has_flow_relationship(self):
        """Task should have flow relationship."""
        mapper = inspect(Task)
        relationships = {rel.key: rel for rel in mapper.relationships}

        assert "flow" in relationships
        assert relationships["flow"].direction.name == "MANYTOONE"

    def test_task_has_subtasks_relationship(self):
        """Task should have subtasks relationship."""
        mapper = inspect(Task)
        relationships = {rel.key: rel for rel in mapper.relationships}

        assert "subtasks" in relationships

    def test_task_flow_id_foreign_key(self):
        """Task.flow_id should be a foreign key to flows.id."""
        mapper = inspect(Task)
        flow_id_col = mapper.columns["flow_id"]

        # Check if it has foreign key constraint
        assert len(flow_id_col.foreign_keys) > 0
        fk = list(flow_id_col.foreign_keys)[0]
        assert "flows" in str(fk.column)
        assert "id" in str(fk.column)

    def test_task_result_default_empty_string(self):
        """Task result should default to empty string."""
        mapper = inspect(Task)
        result_col = mapper.columns["result"]
        assert result_col.default is not None

    def test_task_has_indexes(self):
        """Task should have indexes on status, title, and flow_id."""
        # Access indexes via table_args which is a tuple of Index objects
        table_args = Task.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_tasks_status" in index_names
            assert "ix_tasks_title" in index_names
            assert "ix_tasks_flow_id" in index_names

    def test_task_timestamps_not_nullable(self):
        """created_at and updated_at should NOT be nullable."""
        mapper = inspect(Task)
        assert mapper.columns["created_at"].nullable is False
        assert mapper.columns["updated_at"].nullable is False


class TestSubtaskModel:
    """Unit tests for Subtask model structure."""

    def test_subtask_tablename(self):
        """Subtask model should have correct table name."""
        assert Subtask.__tablename__ == "subtasks"

    def test_subtask_has_all_columns(self):
        """Subtask should have all required columns."""
        mapper = inspect(Subtask)
        column_names = {col.key for col in mapper.columns}

        required_columns = {
            "id",
            "status",
            "title",
            "description",
            "result",
            "context",
            "task_id",
            "created_at",
            "updated_at",
        }

        assert required_columns.issubset(column_names)

    def test_subtask_has_task_relationship(self):
        """Subtask should have task relationship."""
        mapper = inspect(Subtask)
        relationships = {rel.key: rel for rel in mapper.relationships}

        assert "task" in relationships
        assert relationships["task"].direction.name == "MANYTOONE"

    def test_subtask_task_id_foreign_key(self):
        """Subtask.task_id should be a foreign key to tasks.id."""
        mapper = inspect(Subtask)
        task_id_col = mapper.columns["task_id"]

        # Check if it has foreign key constraint
        assert len(task_id_col.foreign_keys) > 0
        fk = list(task_id_col.foreign_keys)[0]
        assert "tasks" in str(fk.column)
        assert "id" in str(fk.column)

    def test_subtask_context_default_empty_string(self):
        """Subtask context should default to empty string."""
        mapper = inspect(Subtask)
        context_col = mapper.columns["context"]
        assert context_col.default is not None

    def test_subtask_result_default_empty_string(self):
        """Subtask result should default to empty string."""
        mapper = inspect(Subtask)
        result_col = mapper.columns["result"]
        assert result_col.default is not None

    def test_subtask_has_indexes(self):
        """Subtask should have indexes on status, title, and task_id."""
        # Access indexes via table_args which is a tuple of Index objects
        table_args = Subtask.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_subtasks_status" in index_names
            assert "ix_subtasks_title" in index_names
            assert "ix_subtasks_task_id" in index_names

    def test_subtask_timestamps_not_nullable(self):
        """created_at and updated_at should NOT be nullable."""
        mapper = inspect(Subtask)
        assert mapper.columns["created_at"].nullable is False
        assert mapper.columns["updated_at"].nullable is False


class TestModelRelationships:
    """Unit tests for model relationships and cascade behavior."""

    def test_flow_tasks_cascade_delete(self):
        """Flow.tasks relationship should have cascade delete orphan."""
        mapper = inspect(Flow)
        tasks_rel = mapper.relationships["tasks"]

        # Check cascade configuration
        assert "delete-orphan" in tasks_rel.cascade

    def test_task_subtasks_cascade_delete(self):
        """Task.subtasks relationship should have cascade delete orphan."""
        mapper = inspect(Task)
        subtasks_rel = mapper.relationships["subtasks"]

        # Check cascade configuration
        assert "delete-orphan" in subtasks_rel.cascade

    def test_flow_containers_cascade_delete(self):
        """Flow.containers relationship should have cascade delete orphan."""
        mapper = inspect(Flow)
        containers_rel = mapper.relationships["containers"]

        assert "delete-orphan" in containers_rel.cascade

    def test_flow_toolcalls_cascade_delete(self):
        """Flow.toolcalls relationship should have cascade delete orphan."""
        mapper = inspect(Flow)
        toolcalls_rel = mapper.relationships["toolcalls"]

        assert "delete-orphan" in toolcalls_rel.cascade

    def test_flow_msgchains_cascade_delete(self):
        """Flow.msgchains relationship should have cascade delete orphan."""
        mapper = inspect(Flow)
        msgchains_rel = mapper.relationships["msgchains"]

        assert "delete-orphan" in msgchains_rel.cascade

    def test_flow_msglogs_cascade_delete(self):
        """Flow.msglogs relationship should have cascade delete orphan."""
        mapper = inspect(Flow)
        msglogs_rel = mapper.relationships["msglogs"]

        assert "delete-orphan" in msglogs_rel.cascade

    def test_container_termlogs_cascade_delete(self):
        """Container.termlogs relationship should have cascade delete orphan."""
        mapper = inspect(Container)
        termlogs_rel = mapper.relationships["termlogs"]

        assert "delete-orphan" in termlogs_rel.cascade

    def test_flow_no_user_id_column(self):
        """Flow model should NOT have user_id column."""
        mapper = inspect(Flow)
        column_names = {col.key for col in mapper.columns}

        assert "user_id" not in column_names


class TestModelTypes:
    """Unit tests for model column types."""

    def test_flow_status_enum_type(self):
        """Flow status should be proper enum type."""
        mapper = inspect(Flow)
        status_col = mapper.columns["status"]

        # Should be an Enum type - cast to access enum_class

        enum_type = cast("SQLEnum", status_col.type)
        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == FlowStatus

    def test_task_status_enum_type(self):
        """Task status should be proper enum type."""
        mapper = inspect(Task)
        status_col = mapper.columns["status"]

        # Should be an Enum type - cast to access enum_class

        enum_type = cast("SQLEnum", status_col.type)
        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == TaskStatus

    def test_subtask_status_enum_type(self):
        """Subtask status should be proper enum type."""
        mapper = inspect(Subtask)
        status_col = mapper.columns["status"]

        # Should be an Enum type - cast to access enum_class

        enum_type = cast("SQLEnum", status_col.type)
        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == SubtaskStatus

    def test_container_type_enum_type(self):
        """Container type should be proper enum type."""
        mapper = inspect(Container)
        enum_type = cast("SQLEnum", mapper.columns["type"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == ContainerType

    def test_container_status_enum_type(self):
        """Container status should be proper enum type."""
        mapper = inspect(Container)
        enum_type = cast("SQLEnum", mapper.columns["status"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == ContainerStatus

    def test_toolcall_status_enum_type(self):
        """Toolcall status should be proper enum type."""
        mapper = inspect(Toolcall)
        enum_type = cast("SQLEnum", mapper.columns["status"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == ToolcallStatus

    def test_msgchain_type_enum_type(self):
        """Msgchain type should be proper enum type."""
        mapper = inspect(Msgchain)
        enum_type = cast("SQLEnum", mapper.columns["type"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == MsgchainType

    def test_termlog_type_enum_type(self):
        """Termlog type should be proper enum type."""
        mapper = inspect(Termlog)
        enum_type = cast("SQLEnum", mapper.columns["type"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == TermlogType

    def test_msglog_type_enum_type(self):
        """Msglog type should be proper enum type."""
        mapper = inspect(Msglog)
        enum_type = cast("SQLEnum", mapper.columns["type"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == MsglogType

    def test_msglog_result_format_enum_type(self):
        """Msglog result_format should be proper enum type."""
        mapper = inspect(Msglog)
        enum_type = cast("SQLEnum", mapper.columns["result_format"].type)

        assert hasattr(enum_type, "enum_class")
        assert enum_type.enum_class == MsglogResultFormat

    def test_flow_functions_json_type(self):
        """Flow functions should be JSON type."""
        mapper = inspect(Flow)
        functions_col = mapper.columns["functions"]

        type_name = functions_col.type.__class__.__name__
        assert type_name == "JSON"

    def test_flow_prompts_json_type(self):
        """Flow prompts should be JSON type."""
        mapper = inspect(Flow)
        prompts_col = mapper.columns["prompts"]

        type_name = prompts_col.type.__class__.__name__
        assert type_name == "JSON"

    def test_flow_id_biginteger_type(self):
        """Flow id should be BigInteger type."""
        mapper = inspect(Flow)
        id_col = mapper.columns["id"]

        type_name = id_col.type.__class__.__name__
        assert type_name == "BigInteger"


class TestModelConstraints:
    """Unit tests for model constraints."""

    def test_flow_status_not_nullable(self):
        """Flow status should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["status"].nullable is False

    def test_flow_model_not_nullable(self):
        """Flow model should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["model"].nullable is False

    def test_flow_model_provider_not_nullable(self):
        """Flow model_provider should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["model_provider"].nullable is False

    def test_flow_language_not_nullable(self):
        """Flow language should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["language"].nullable is False

    def test_flow_prompts_not_nullable(self):
        """Flow prompts should NOT be nullable."""
        mapper = inspect(Flow)
        assert mapper.columns["prompts"].nullable is False

    def test_task_status_not_nullable(self):
        """Task status should NOT be nullable."""
        mapper = inspect(Task)
        assert mapper.columns["status"].nullable is False

    def test_task_title_not_nullable(self):
        """Task title should NOT be nullable."""
        mapper = inspect(Task)
        assert mapper.columns["title"].nullable is False

    def test_task_input_not_nullable(self):
        """Task input should NOT be nullable."""
        mapper = inspect(Task)
        assert mapper.columns["input"].nullable is False

    def test_subtask_status_not_nullable(self):
        """Subtask status should NOT be nullable."""
        mapper = inspect(Subtask)
        assert mapper.columns["status"].nullable is False

    def test_subtask_title_not_nullable(self):
        """Subtask title should NOT be nullable."""
        mapper = inspect(Subtask)
        assert mapper.columns["title"].nullable is False

    def test_subtask_description_not_nullable(self):
        """Subtask description should NOT be nullable."""
        mapper = inspect(Subtask)
        assert mapper.columns["description"].nullable is False

    def test_subtask_context_not_nullable(self):
        """Subtask context should NOT be nullable."""
        mapper = inspect(Subtask)
        assert mapper.columns["context"].nullable is False


class TestContainerModel:
    """Unit tests for Container model structure."""

    def test_container_has_all_columns(self):
        mapper = inspect(Container)
        column_names = {col.key for col in mapper.columns}

        assert {
            "id",
            "type",
            "name",
            "image",
            "status",
            "local_id",
            "local_dir",
            "flow_id",
            "created_at",
            "updated_at",
        }.issubset(column_names)

    def test_container_has_relationships(self):
        mapper = inspect(Container)
        relationships = {rel.key for rel in mapper.relationships}

        assert {"flow", "termlogs"}.issubset(relationships)

    def test_container_local_id_is_unique(self):
        mapper = inspect(Container)
        assert mapper.columns["local_id"].unique is True

    def test_container_has_indexes(self):
        table_args = Container.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_containers_type" in index_names
            assert "ix_containers_name" in index_names
            assert "ix_containers_status" in index_names
            assert "ix_containers_flow_id" in index_names

    def test_container_name_default_generates_md5_hex(self):
        """Container name default should generate a 32-char lowercase md5 string."""
        mapper = inspect(Container)
        name_default = mapper.columns["name"].default

        assert name_default is not None
        generated_name = name_default.arg(None)
        assert re.fullmatch(r"[0-9a-f]{32}", generated_name) is not None

    def test_container_has_complete_expected_indexes(self):
        """Container should declare the full expected index set."""
        table_args = Container.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
                "ix_containers_type",
                "ix_containers_name",
                "ix_containers_status",
                "ix_containers_flow_id",
            }


class TestToolcallModel:
    """Unit tests for Toolcall model structure."""

    def test_toolcall_has_all_columns(self):
        mapper = inspect(Toolcall)
        column_names = {col.key for col in mapper.columns}

        assert {
            "id",
            "call_id",
            "status",
            "name",
            "args",
            "result",
            "duration_seconds",
            "flow_id",
            "task_id",
            "subtask_id",
            "created_at",
            "updated_at",
        }.issubset(column_names)

    def test_toolcall_nullable_scope_columns(self):
        mapper = inspect(Toolcall)
        assert mapper.columns["task_id"].nullable is True
        assert mapper.columns["subtask_id"].nullable is True

    def test_toolcall_has_indexes(self):
        table_args = Toolcall.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_toolcalls_name" in index_names
            assert "ix_toolcalls_flow_id" in index_names
            assert "ix_toolcalls_name_status" in index_names
            assert "ix_toolcalls_flow_id_status" in index_names

    def test_toolcall_has_complete_expected_indexes(self):
        """Toolcall should declare the full expected index set."""
        table_args = Toolcall.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
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
            }


class TestMsgchainModel:
    """Unit tests for Msgchain model structure."""

    def test_msgchain_has_all_columns(self):
        mapper = inspect(Msgchain)
        column_names = {col.key for col in mapper.columns}

        assert {
            "id",
            "type",
            "model",
            "model_provider",
            "usage_in",
            "usage_out",
            "usage_cache_in",
            "usage_cache_out",
            "usage_cost_in",
            "usage_cost_out",
            "duration_seconds",
            "chain",
            "flow_id",
            "task_id",
            "subtask_id",
            "created_at",
            "updated_at",
        }.issubset(column_names)

    def test_msgchain_has_indexes(self):
        table_args = Msgchain.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_msgchains_type" in index_names
            assert "ix_msgchains_flow_id" in index_names
            assert "ix_msgchains_type_flow_id" in index_names
            assert "ix_msgchains_type_task_id_subtask_id" in index_names

    def test_msgchain_has_complete_expected_indexes(self):
        """Msgchain should declare the full expected index set."""
        table_args = Msgchain.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
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
            }


class TestTermlogModel:
    """Unit tests for Termlog model structure."""

    def test_termlog_has_all_columns(self):
        mapper = inspect(Termlog)
        column_names = {col.key for col in mapper.columns}

        assert {
            "id",
            "type",
            "text",
            "container_id",
            "flow_id",
            "task_id",
            "subtask_id",
            "created_at",
        }.issubset(column_names)

    def test_termlog_has_container_relationship(self):
        mapper = inspect(Termlog)
        relationships = {rel.key for rel in mapper.relationships}

        assert "container" in relationships

    def test_termlog_has_indexes(self):
        table_args = Termlog.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_termlogs_container_id" in index_names
            assert "ix_termlogs_flow_id" in index_names

    def test_termlog_has_complete_expected_indexes(self):
        """Termlog should declare the full expected index set."""
        table_args = Termlog.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
                "ix_termlogs_type",
                "ix_termlogs_container_id",
                "ix_termlogs_flow_id",
                "ix_termlogs_task_id",
                "ix_termlogs_subtask_id",
            }


class TestMsglogModel:
    """Unit tests for Msglog model structure."""

    def test_msglog_has_all_columns(self):
        mapper = inspect(Msglog)
        column_names = {col.key for col in mapper.columns}

        assert {
            "id",
            "type",
            "message",
            "result",
            "result_format",
            "flow_id",
            "task_id",
            "subtask_id",
            "created_at",
        }.issubset(column_names)

    def test_msglog_result_default_exists(self):
        mapper = inspect(Msglog)
        assert mapper.columns["result"].default is not None

    def test_msglog_has_indexes(self):
        table_args = Msglog.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert "ix_msglogs_flow_id" in index_names
            assert "ix_msglogs_result_format" in index_names

    def test_msglog_has_complete_expected_indexes(self):
        """Msglog should declare the full expected index set."""
        table_args = Msglog.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
                "ix_msglogs_type",
                "ix_msglogs_flow_id",
                "ix_msglogs_task_id",
                "ix_msglogs_subtask_id",
                "ix_msglogs_result_format",
            }


class TestVectorStoreModel:
    """Unit tests for VectorStore model structure."""

    def test_vector_store_tablename(self):
        assert VectorStore.__tablename__ == "vector_store"

    def test_vector_store_has_all_columns(self):
        mapper = inspect(VectorStore)
        column_names = {col.key for col in mapper.columns}

        assert {"id", "content", "metadata_", "embedding", "created_at"}.issubset(column_names)

    def test_vector_store_embedding_dimension(self):
        mapper = inspect(VectorStore)
        embedding_col = mapper.columns["embedding"]
        assert getattr(embedding_col.type, "dim", None) == 1536

    def test_vector_store_metadata_default(self):
        mapper = inspect(VectorStore)
        metadata_col = mapper.columns["metadata_"]
        assert metadata_col.default is not None

    def test_vector_store_has_complete_expected_indexes(self):
        table_args = VectorStore.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
                "ix_vector_store_embedding_ivfflat",
                "ix_vector_store_metadata_flow_id",
                "ix_vector_store_metadata_task_id",
                "ix_vector_store_metadata_doc_type",
            }
