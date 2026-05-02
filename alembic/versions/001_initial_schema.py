"""Initial runtime schema for LusitAI MCP execution engine.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-04-19 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_enums() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'flow_status') THEN
                CREATE TYPE flow_status AS ENUM ('created', 'running', 'waiting', 'finished', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
                CREATE TYPE task_status AS ENUM ('created', 'running', 'waiting', 'finished', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subtask_status') THEN
                CREATE TYPE subtask_status AS ENUM ('created', 'running', 'waiting', 'finished', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'container_type') THEN
                CREATE TYPE container_type AS ENUM ('primary', 'secondary');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'container_status') THEN
                CREATE TYPE container_status AS ENUM ('starting', 'running', 'stopped', 'deleted', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'toolcall_status') THEN
                CREATE TYPE toolcall_status AS ENUM ('received', 'running', 'finished', 'failed');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'msgchain_type') THEN
                CREATE TYPE msgchain_type AS ENUM (
                    'primary_agent', 'reporter', 'generator', 'refiner', 'reflector',
                    'enricher', 'adviser', 'coder', 'memorist', 'searcher', 'installer',
                    'pentester', 'summarizer', 'tool_call_fixer'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'termlog_type') THEN
                CREATE TYPE termlog_type AS ENUM ('stdin', 'stdout', 'stderr');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'msglog_type') THEN
                CREATE TYPE msglog_type AS ENUM (
                    'thoughts', 'browser', 'terminal', 'file', 'search',
                    'advice', 'input', 'done', 'answer', 'report'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'msglog_result_format') THEN
                CREATE TYPE msglog_result_format AS ENUM ('terminal', 'plain', 'markdown');
            END IF;
        END
        $$;
        """
    )


def _create_update_trigger_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_modified_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        """
    )


def _create_update_trigger(table_name: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS tr_{table_name}_updated_at ON {table_name}")
    op.execute(
        f"""
        CREATE TRIGGER tr_{table_name}_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION update_modified_column()
        """
    )


def _drop_update_trigger(table_name: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS tr_{table_name}_updated_at ON {table_name};")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_enums()

    op.create_table(
        "flows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="flow_status", create_type=False),
            server_default=sa.text("'created'::flow_status"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("functions", sa.JSON(), nullable=False),
        sa.Column("prompts", sa.JSON(), nullable=False),
        sa.Column("tool_call_id_template", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="task_status", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "subtasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="subtask_status", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "containers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(name="container_type", create_type=False),
            server_default=sa.text("'primary'::container_type"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="container_status", create_type=False),
            server_default=sa.text("'starting'::container_status"),
            nullable=False,
        ),
        sa.Column("local_id", sa.Text(), nullable=True),
        sa.Column("local_dir", sa.Text(), nullable=True),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_id"),
    )

    op.create_table(
        "toolcalls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="toolcall_status", create_type=False),
            server_default=sa.text("'received'::toolcall_status"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("subtask_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtask_id"], ["subtasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "msgchains",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(name="msgchain_type", create_type=False),
            server_default=sa.text("'primary_agent'::msgchain_type"),
            nullable=False,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("usage_in", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("usage_out", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("usage_cache_in", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("usage_cache_out", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("usage_cost_in", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("usage_cost_out", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("duration_seconds", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("chain", sa.JSON(), nullable=False),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("subtask_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtask_id"], ["subtasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "termlogs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(name="termlog_type", create_type=False),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("container_id", sa.BigInteger(), nullable=False),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("subtask_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["container_id"], ["containers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtask_id"], ["subtasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "msglogs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(name="msglog_type", create_type=False),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column(
            "result_format",
            postgresql.ENUM(name="msglog_result_format", create_type=False),
            server_default=sa.text("'plain'::msglog_result_format"),
            nullable=False,
        ),
        sa.Column("flow_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("subtask_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtask_id"], ["subtasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "vector_store",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_", sa.JSON(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_flows_status", "flows", ["status"], unique=False)
    op.create_index("ix_flows_title", "flows", ["title"], unique=False)

    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_title", "tasks", ["title"], unique=False)
    op.create_index("ix_tasks_flow_id", "tasks", ["flow_id"], unique=False)

    op.create_index("ix_subtasks_status", "subtasks", ["status"], unique=False)
    op.create_index("ix_subtasks_title", "subtasks", ["title"], unique=False)
    op.create_index("ix_subtasks_task_id", "subtasks", ["task_id"], unique=False)

    op.create_index("ix_containers_type", "containers", ["type"], unique=False)
    op.create_index("ix_containers_name", "containers", ["name"], unique=False)
    op.create_index("ix_containers_status", "containers", ["status"], unique=False)
    op.create_index("ix_containers_flow_id", "containers", ["flow_id"], unique=False)

    op.create_index("ix_toolcalls_call_id", "toolcalls", ["call_id"], unique=False)
    op.create_index("ix_toolcalls_status", "toolcalls", ["status"], unique=False)
    op.create_index("ix_toolcalls_name", "toolcalls", ["name"], unique=False)
    op.create_index("ix_toolcalls_flow_id", "toolcalls", ["flow_id"], unique=False)
    op.create_index("ix_toolcalls_task_id", "toolcalls", ["task_id"], unique=False)
    op.create_index("ix_toolcalls_subtask_id", "toolcalls", ["subtask_id"], unique=False)
    op.create_index("ix_toolcalls_created_at", "toolcalls", ["created_at"], unique=False)
    op.create_index("ix_toolcalls_updated_at", "toolcalls", ["updated_at"], unique=False)
    op.create_index("ix_toolcalls_flow_id_status", "toolcalls", ["flow_id", "status"], unique=False)
    op.create_index("ix_toolcalls_name_status", "toolcalls", ["name", "status"], unique=False)
    op.create_index("ix_toolcalls_name_flow_id", "toolcalls", ["name", "flow_id"], unique=False)
    op.create_index(
        "ix_toolcalls_status_updated_at",
        "toolcalls",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_index("ix_msgchains_type", "msgchains", ["type"], unique=False)
    op.create_index("ix_msgchains_flow_id", "msgchains", ["flow_id"], unique=False)
    op.create_index("ix_msgchains_task_id", "msgchains", ["task_id"], unique=False)
    op.create_index("ix_msgchains_subtask_id", "msgchains", ["subtask_id"], unique=False)
    op.create_index("ix_msgchains_created_at", "msgchains", ["created_at"], unique=False)
    op.create_index("ix_msgchains_model_provider", "msgchains", ["model_provider"], unique=False)
    op.create_index("ix_msgchains_model", "msgchains", ["model"], unique=False)
    op.create_index("ix_msgchains_type_flow_id", "msgchains", ["type", "flow_id"], unique=False)
    op.create_index(
        "ix_msgchains_created_at_flow_id",
        "msgchains",
        ["created_at", "flow_id"],
        unique=False,
    )
    op.create_index(
        "ix_msgchains_type_created_at", "msgchains", ["type", "created_at"], unique=False
    )
    op.create_index(
        "ix_msgchains_type_task_id_subtask_id",
        "msgchains",
        ["type", "task_id", "subtask_id"],
        unique=False,
    )

    op.create_index("ix_termlogs_type", "termlogs", ["type"], unique=False)
    op.create_index("ix_termlogs_container_id", "termlogs", ["container_id"], unique=False)
    op.create_index("ix_termlogs_flow_id", "termlogs", ["flow_id"], unique=False)
    op.create_index("ix_termlogs_task_id", "termlogs", ["task_id"], unique=False)
    op.create_index("ix_termlogs_subtask_id", "termlogs", ["subtask_id"], unique=False)

    op.create_index("ix_msglogs_type", "msglogs", ["type"], unique=False)
    op.create_index("ix_msglogs_flow_id", "msglogs", ["flow_id"], unique=False)
    op.create_index("ix_msglogs_task_id", "msglogs", ["task_id"], unique=False)
    op.create_index("ix_msglogs_subtask_id", "msglogs", ["subtask_id"], unique=False)
    op.create_index("ix_msglogs_result_format", "msglogs", ["result_format"], unique=False)

    op.create_index(
        "ix_vector_store_embedding_ivfflat",
        "vector_store",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_vector_store_metadata_flow_id",
        "vector_store",
        [sa.text("(metadata_->>'flow_id')")],
        unique=False,
    )
    op.create_index(
        "ix_vector_store_metadata_task_id",
        "vector_store",
        [sa.text("(metadata_->>'task_id')")],
        unique=False,
    )
    op.create_index(
        "ix_vector_store_metadata_doc_type",
        "vector_store",
        [sa.text("(metadata_->>'doc_type')")],
        unique=False,
    )

    _create_update_trigger_function()
    _create_update_trigger("flows")
    _create_update_trigger("tasks")
    _create_update_trigger("subtasks")
    _create_update_trigger("containers")
    _create_update_trigger("toolcalls")
    _create_update_trigger("msgchains")


def downgrade() -> None:
    _drop_update_trigger("msgchains")
    _drop_update_trigger("toolcalls")
    _drop_update_trigger("containers")
    _drop_update_trigger("subtasks")
    _drop_update_trigger("tasks")
    _drop_update_trigger("flows")
    op.execute("DROP FUNCTION IF EXISTS update_modified_column()")

    op.drop_index("ix_vector_store_metadata_doc_type", table_name="vector_store")
    op.drop_index("ix_vector_store_metadata_task_id", table_name="vector_store")
    op.drop_index("ix_vector_store_metadata_flow_id", table_name="vector_store")
    op.drop_index("ix_vector_store_embedding_ivfflat", table_name="vector_store")

    op.drop_index("ix_msglogs_result_format", table_name="msglogs")
    op.drop_index("ix_msglogs_subtask_id", table_name="msglogs")
    op.drop_index("ix_msglogs_task_id", table_name="msglogs")
    op.drop_index("ix_msglogs_flow_id", table_name="msglogs")
    op.drop_index("ix_msglogs_type", table_name="msglogs")

    op.drop_index("ix_termlogs_subtask_id", table_name="termlogs")
    op.drop_index("ix_termlogs_task_id", table_name="termlogs")
    op.drop_index("ix_termlogs_flow_id", table_name="termlogs")
    op.drop_index("ix_termlogs_container_id", table_name="termlogs")
    op.drop_index("ix_termlogs_type", table_name="termlogs")

    op.drop_index("ix_msgchains_type_task_id_subtask_id", table_name="msgchains")
    op.drop_index("ix_msgchains_type_created_at", table_name="msgchains")
    op.drop_index("ix_msgchains_created_at_flow_id", table_name="msgchains")
    op.drop_index("ix_msgchains_type_flow_id", table_name="msgchains")
    op.drop_index("ix_msgchains_model", table_name="msgchains")
    op.drop_index("ix_msgchains_model_provider", table_name="msgchains")
    op.drop_index("ix_msgchains_created_at", table_name="msgchains")
    op.drop_index("ix_msgchains_subtask_id", table_name="msgchains")
    op.drop_index("ix_msgchains_task_id", table_name="msgchains")
    op.drop_index("ix_msgchains_flow_id", table_name="msgchains")
    op.drop_index("ix_msgchains_type", table_name="msgchains")

    op.drop_index("ix_toolcalls_status_updated_at", table_name="toolcalls")
    op.drop_index("ix_toolcalls_name_flow_id", table_name="toolcalls")
    op.drop_index("ix_toolcalls_name_status", table_name="toolcalls")
    op.drop_index("ix_toolcalls_flow_id_status", table_name="toolcalls")
    op.drop_index("ix_toolcalls_updated_at", table_name="toolcalls")
    op.drop_index("ix_toolcalls_created_at", table_name="toolcalls")
    op.drop_index("ix_toolcalls_subtask_id", table_name="toolcalls")
    op.drop_index("ix_toolcalls_task_id", table_name="toolcalls")
    op.drop_index("ix_toolcalls_flow_id", table_name="toolcalls")
    op.drop_index("ix_toolcalls_name", table_name="toolcalls")
    op.drop_index("ix_toolcalls_status", table_name="toolcalls")
    op.drop_index("ix_toolcalls_call_id", table_name="toolcalls")

    op.drop_index("ix_containers_flow_id", table_name="containers")
    op.drop_index("ix_containers_status", table_name="containers")
    op.drop_index("ix_containers_name", table_name="containers")
    op.drop_index("ix_containers_type", table_name="containers")

    op.drop_index("ix_subtasks_task_id", table_name="subtasks")
    op.drop_index("ix_subtasks_title", table_name="subtasks")
    op.drop_index("ix_subtasks_status", table_name="subtasks")

    op.drop_index("ix_tasks_flow_id", table_name="tasks")
    op.drop_index("ix_tasks_title", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")

    op.drop_index("ix_flows_title", table_name="flows")
    op.drop_index("ix_flows_status", table_name="flows")

    op.drop_table("vector_store")
    op.drop_table("msglogs")
    op.drop_table("termlogs")
    op.drop_table("msgchains")
    op.drop_table("toolcalls")
    op.drop_table("containers")
    op.drop_table("subtasks")
    op.drop_table("tasks")
    op.drop_table("flows")

    op.execute("DROP TYPE IF EXISTS msglog_result_format")
    op.execute("DROP TYPE IF EXISTS msglog_type")
    op.execute("DROP TYPE IF EXISTS termlog_type")
    op.execute("DROP TYPE IF EXISTS msgchain_type")
    op.execute("DROP TYPE IF EXISTS toolcall_status")
    op.execute("DROP TYPE IF EXISTS container_status")
    op.execute("DROP TYPE IF EXISTS container_type")
    op.execute("DROP TYPE IF EXISTS subtask_status")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS flow_status")
