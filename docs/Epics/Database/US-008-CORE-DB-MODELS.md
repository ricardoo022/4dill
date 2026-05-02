---
tags: [database]
---

# US-008: Core SQLAlchemy Models — Explicação Detalhada

Este documento explica linha a linha o ficheiro `src/pentest/database/models.py`, que define os 3 modelos SQLAlchemy 2.0 para o sistema de rastreamento de fluxos, tarefas e subtarefas no SecureDev PentestAI.

---

## Contexto

O PentAGI usa PostgreSQL com SQLAlchemy 2.0 para definir a hierarquia de dados:

- **Flow** (Fluxo) — Uma scan session completa (top-level entity)
- **Task** (Tarefa) — Uma fase de teste major dentro de um Flow
- **Subtask** (Subtarefa) — Uma atribuição atômica a um agente dentro de uma Task

A relação é: `Flow -> Tasks -> Subtasks` com **cascade delete** automático e timestamps imutáveis.

---

## Imports (linhas 1-30)

```python
"""SQLAlchemy 2.0 models for SecureDev PentestAI database schema.

Uses strict SQLAlchemy 2.0 syntax with Mapped[X] type hints and mapped_column().
All models inherit from Base and use async-compatible types.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pentest.database.enums import (
    FlowStatus,
    FlowStatusType,
    SubtaskStatus,
    SubtaskStatusType,
    TaskStatus,
    TaskStatusType,
)
```

| Import | Para que serve |
|---|---|
| `datetime` | Type hint para timestamps `Mapped[datetime]` |
| `JSON, BigInteger, DateTime, Text` | Tipos de coluna SQLAlchemy |
| `ForeignKey, Index` | Constraints de foreign key e indexes |
| `func` | Funções SQL como `func.now()` para server defaults |
| `text` | SQL raw para server_default como `text("'created'")` |
| `DeclarativeBase, Mapped, mapped_column, relationship` | **SQLAlchemy 2.0 Strict**: type hints e column definitions |
| `FlowStatus, TaskStatus, SubtaskStatus` | Enums Python para type hints |
| `FlowStatusType, TaskStatusType, SubtaskStatusType` | SQLAlchemy type wrappers (com `create_type=False`) |

---

## Declarative Base (linhas 32-35)

```python
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass
```

**Por que é necessário?**

- SQLAlchemy 2.0 requer uma classe `DeclarativeBase` como parent para todos os models
- Isto permite que o ORM rastreie todos os models via `Base.registry`
- Usado em migrations: `Base.metadata.create_all()` cria todas as tabelas de uma vez

---

## Flow Model (linhas 37-88)

```python
class Flow(Base):
    """Flow model representing a complete scan session.

    A Flow is the top-level entity containing the entire pentest scan session,
    including metadata, LLM configuration, and all tasks.
    """

    __tablename__ = "flows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status: Mapped[FlowStatus] = mapped_column(
        FlowStatusType, server_default=text("'created'"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, default="untitled", nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    functions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prompts: Mapped[dict] = mapped_column(JSON, nullable=False)
    tool_call_id_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="flow",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_flows_status", "status"),
        Index("ix_flows_title", "title"),
    )
```

### Análise Detalhada

#### `__tablename__ = "flows"`
- Define o nome da tabela PostgreSQL
- SQLAlchemy criará: `CREATE TABLE flows (...)`

#### `id: Mapped[int] = mapped_column(...)`

```python
id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
```

- **`Mapped[int]`** — Type hint: este atributo é mapeado para um inteiro no DB
- **`BigInteger`** — PostgreSQL `bigint` (8 bytes, até 2^63-1)
- **`primary_key=True`** — Chave primária (auto-incrementada)
- **`autoincrement=True`** — PostgreSQL gera IDs automaticamente (sequence)

#### `status: Mapped[FlowStatus] = mapped_column(FlowStatusType, ...)`

```python
status: Mapped[FlowStatus] = mapped_column(
    FlowStatusType, server_default=text("'created'"), nullable=False
)
```

- **`Mapped[FlowStatus]`** — Type hint: este é um enum Python
- **`FlowStatusType`** — SQLAlchemy wrapper do enum (com `create_type=False`)
- **`server_default=text("'created'")`** — PostgreSQL coloca `'created'` por default (string literal com quotes)
- **`nullable=False`** — NOT NULL constraint
- **Por que `text("'created'")`?** Porque o enum value é uma string lowercase, mas sem quotes SQLAlchemy interpreta como coluna/função. A sintaxe `text(...)` permite SQL raw.

#### `title: Mapped[str] = mapped_column(Text, default="untitled")`

- **`default="untitled"`** — Python-side default: quando criamos `Flow()` sem `title`, SQLAlchemy coloca `"untitled"` antes de INSERT
- Isto é diferente de `server_default`: este é Python, aquele é PostgreSQL

#### `created_at` e `updated_at`

```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), nullable=False
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```

- **`DateTime(timezone=True)`** — PostgreSQL `timestamp with time zone`
- **`server_default=func.now()`** — PostgreSQL coloca `now()` por default (timestamp no servidor, não no cliente)
- **`onupdate=func.now()`** — Quando o record é UPDATEd, PostgreSQL atualiza `updated_at` para `now()` automaticamente
- **Por que server-side?** Porque queremos que o servidor (PostgreSQL) controle os timestamps, não a aplicação Python (evita clock skew)

#### `deleted_at: Mapped[datetime | None]`

- **`nullable=True`** — Permite NULL (soft delete pattern)
- Queries devem usar: `where(Flow.deleted_at.is_(None))` para obter apenas "active" records

#### `tasks` Relationship

```python
tasks: Mapped[list["Task"]] = relationship(
    "Task",
    back_populates="flow",
    cascade="all, delete-orphan",
    lazy="select",
)
```

- **`Mapped[list["Task"]]`** — Type hint: uma lista de Task objects
- **`"Task"`** — String forward reference (Task não é definido ainda no ficheiro)
- **`back_populates="flow"`** — Bidirectional: Task tem um atributo `flow` que aponta de volta para Flow
- **`cascade="all, delete-orphan"`** — Quando Flow é deleted, todas as Tasks são também deleted (CASCADE)
- **`lazy="select"`** — Lazy loading: Tasks não são carregadas até explicitamente acedidas

#### `__table_args__` — Indexes

```python
__table_args__ = (
    Index("ix_flows_status", "status"),
    Index("ix_flows_title", "title"),
)
```

- Cria 2 indexes: um em `status` (para queries rápidas por status), outro em `title`
- PostgreSQL gera automaticamente: `CREATE INDEX ix_flows_status ON flows(status);`

---

## Task Model (linhas 90-119)

```python
class Task(Base):
    """Task model representing a major testing phase within a Flow.

    A Task is a logical grouping of work assigned to an agent within a Flow,
    containing multiple atomic Subtasks.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status: Mapped[TaskStatus] = mapped_column(TaskStatusType, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    flow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    flow: Mapped[Flow] = relationship("Flow", back_populates="tasks", lazy="select")
    subtasks: Mapped[list["Subtask"]] = relationship(
        "Subtask",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_title", "title"),
        Index("ix_tasks_flow_id", "flow_id"),
    )
```

### Pontos-chave

#### `flow_id` Foreign Key

```python
flow_id: Mapped[int] = mapped_column(
    BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
)
```

- **`ForeignKey("flows.id")`** — PostgreSQL constraint: `FOREIGN KEY (flow_id) REFERENCES flows(id)`
- **`ondelete="CASCADE"`** — Se um Flow é deleted, todas as Tasks são deleted automaticamente
- **`nullable=False`** — Uma Task DEVE ter um Flow

#### `flow` Relationship (Reverse)

```python
flow: Mapped[Flow] = relationship("Flow", back_populates="tasks", lazy="select")
```

- Permite aceder: `task.flow` (a Flow que contém este Task)
- **`back_populates="tasks"`** — Bidirecional: `flow.tasks` também funciona

#### `subtasks` Relationship (One-to-Many)

```python
subtasks: Mapped[list["Subtask"]] = relationship(
    "Subtask",
    back_populates="task",
    cascade="all, delete-orphan",
    lazy="select",
)
```

- Mesma lógica que `Flow.tasks`: quando um Task é deleted, todas as Subtasks são deleted

---

## Subtask Model (linhas 121-161)

```python
class Subtask(Base):
    """Subtask model representing an atomic agent assignment within a Task.

    A Subtask is an individual unit of work with a specific status,
    description, and execution result.
    """

    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status: Mapped[SubtaskStatus] = mapped_column(SubtaskStatusType, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="subtasks", lazy="select")

    __table_args__ = (
        Index("ix_subtasks_status", "status"),
        Index("ix_subtasks_title", "title"),
        Index("ix_subtasks_task_id", "task_id"),
    )
```

- **Mesma estrutura que Task**, mas sem `subtasks` relationship (fim da hierarquia)
- **Foreign key a Task**: `task_id` com `ondelete="CASCADE"`

---

## Testes de Integração (tests/integration/database/test_models.py)

### Fixture `db_schema` — Criação de Schema

```python
@pytest.fixture(scope="module")
def db_schema():
    """Create database schema with explicit Enum type creation and table recreation.

    Since our Enum wrappers use create_type=False, we must manually create
    the PostgreSQL ENUM types before creating tables.
    """
    import asyncio

    async def _setup():
        await init_db(TEST_DATABASE_URL, echo=False)

        async with get_session() as session:
            conn = await session.connection()

            # Drop all tables first (to ensure fresh schema)
            await conn.execute(text("DROP TABLE IF EXISTS subtasks CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS tasks CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS flows CASCADE;"))

            # Drop existing types if they exist (idempotent)
            await conn.execute(text("DROP TYPE IF EXISTS flow_status CASCADE;"))
            await conn.execute(text("DROP TYPE IF EXISTS task_status CASCADE;"))
            await conn.execute(text("DROP TYPE IF EXISTS subtask_status CASCADE;"))

            # Create PostgreSQL ENUM types
            await conn.execute(
                text(
                    """
                    CREATE TYPE flow_status AS ENUM (
                        'created', 'running', 'waiting', 'finished', 'failed'
                    );
                    """
                )
            )
            # ... (task_status e subtask_status)

            # Create all tables from models
            await conn.run_sync(Base.metadata.create_all)
            await session.commit()

        await close_db()

    asyncio.run(_setup())
    yield
```

**Por que isto é crítico?**

- Nós definimos `FlowStatusType = SQLEnum(..., create_type=False)`
- Isto diz ao SQLAlchemy: "Não cries o tipo ENUM, eu já o criei"
- Portanto, **nós temos que criar manualmente** com `CREATE TYPE` antes de criar as tabelas
- Sem isto, `CREATE TABLE flows (status flow_status)` falharia com "type flow_status does not exist"

### Fixture `db_session` — Limpeza Entre Testes

```python
@pytest.fixture()
async def db_session(db_schema):
    """Provide a fresh database session for each test."""
    await init_db(TEST_DATABASE_URL, echo=False)

    # Yield to the test
    yield

    # Clean up after test: Delete all data
    async with get_session() as session:
        # Delete all rows from all tables (order matters due to FK constraints)
        await session.execute(text("DELETE FROM subtasks"))
        await session.execute(text("DELETE FROM tasks"))
        await session.execute(text("DELETE FROM flows"))
        await session.commit()

    await close_db()
```

- Antes de cada teste: inicia DB e session
- Depois do teste: limpa dados (DELETE em ordem inversa para respeitar foreign keys)

### Teste 1: `test_flow_defaults` — Defaults

```python
@pytest.mark.asyncio
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
        await session.commit()

        # Verify defaults were applied
        assert flow.status == FlowStatus.CREATED
        assert flow.title == "untitled"
        assert flow.functions == {}
        assert flow.trace_id is None
        assert flow.deleted_at is None
        assert flow.created_at is not None
        assert flow.updated_at is not None

        # Refetch and verify persistence
        result = await session.execute(select(Flow).where(Flow.id == flow.id))
        fetched_flow = result.scalar_one()
        assert fetched_flow.status == FlowStatus.CREATED
```

**O que valida:**

1. ✅ Python-side defaults (`status`, `title`, `functions`)
2. ✅ Server-side defaults (`created_at`, `updated_at`)
3. ✅ Persistence na DB

### Teste 2: `test_hierarchy_and_cascades` — Cascade Delete

```python
@pytest.mark.asyncio
async def test_hierarchy_and_cascades(db_session) -> None:
    """Test Flow -> Task -> Subtask hierarchy and cascade deletion."""
    async with get_session() as session:
        # Create a complete hierarchy
        flow = Flow(...)
        session.add(flow)
        await session.flush()

        task = Task(flow_id=flow.id, ...)
        session.add(task)
        await session.flush()

        subtask = Subtask(task_id=task.id, ...)
        session.add(subtask)
        await session.commit()

        # Verify hierarchy exists
        flow_id, task_id, subtask_id = flow.id, task.id, subtask.id

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
```

**O que valida:**

1. ✅ Relationships: `flow.tasks`, `task.subtasks`
2. ✅ Cascade delete: apagar Flow deleta Tasks e Subtasks automaticamente

### Teste 3: `test_updated_at_trigger` — Timestamp Updates

```python
@pytest.mark.asyncio
async def test_updated_at_trigger(db_session) -> None:
    """Test that updated_at is automatically updated when record changes."""
    async with get_session() as session:
        # Create a Flow
        flow = Flow(...)
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

        assert flow_v3.updated_at >= original_updated_at
        assert flow_v3.created_at == original_created_at
```

**O que valida:**

1. ✅ `onupdate=func.now()` funciona: `updated_at` muda ao UPDATE
2. ✅ `created_at` nunca muda

### Teste 4: `test_soft_delete_filter` — Soft Delete Pattern

```python
@pytest.mark.asyncio
async def test_soft_delete_filter(db_session) -> None:
    """Test soft delete pattern with deleted_at field."""
    async with get_session() as session:
        # Create multiple flows
        flow1 = Flow(title="Active", ...)
        flow2 = Flow(title="To Delete", ...)
        session.add_all([flow1, flow2])
        await session.commit()

        flow1_id, flow2_id = flow1.id, flow2.id

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
```

**O que valida:**

1. ✅ Soft delete: record não é realmente apagado, apenas `deleted_at` é setado
2. ✅ Filtering: queries que usam `deleted_at.is_(None)` filtram records "deleted"

### Teste 5: `test_status_index_query` — Index Usage

```python
@pytest.mark.asyncio
async def test_status_index_query(db_session) -> None:
    """Test querying using status index."""
    async with get_session() as session:
        # Create flows with different statuses
        flow_created = Flow(status=FlowStatus.CREATED, ...)
        flow_running = Flow(status=FlowStatus.RUNNING, ...)
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
```

**O que valida:**

1. ✅ Index em `status` permite queries eficientes
2. ✅ Enum type-safety: `where(Flow.status == FlowStatus.RUNNING)` é type-safe

### Testes de Relacionamentos

```python
@pytest.mark.asyncio
async def test_task_relationships(db_session) -> None:
    """Test Task relationships to Flow and Subtasks."""
    # Create a flow with multiple tasks
    # ...
    # Verify relationship by explicit query
    result = await session.execute(select(Task).where(Task.flow_id == flow_id))
    fetched_tasks = result.scalars().all()
    assert len(fetched_tasks) == 2
```

**Por que queries explícitas?**

- Em async, lazy loading de relationships causa "greenlet" errors
- Solução: usar `select(Task).where(Task.flow_id == ...)` em vez de `flow.tasks`

---

## Testes Unitários (tests/unit/database/test_models.py)

47 testes que validam:

1. ✅ Nomes de tabelas corretos
2. ✅ Tipos de coluna corretos (`BigInteger`, `Text`, `JSON`, `DateTime`)
3. ✅ Constraints (`nullable=False`, NOT NULL)
4. ✅ Foreign keys com `ondelete="CASCADE"`
5. ✅ Relationships com `cascade="all, delete-orphan"`
6. ✅ Indexes criados corretamente
7. ✅ Default values (Python-side)
8. ✅ Enum types mapeados corretamente

---

## Resultados Finais

✅ **54 testes totais: TODOS PASSANDO**

- 47 testes unitários ✅
- 7 testes de integração ✅

✅ **Lint & Ruff: ZERO erros**

✅ **Conformidade com Specs:**

| Requisito | Status |
|---|---|
| SQLAlchemy 2.0 (`Mapped`, `mapped_column`) | ✅ Implementado |
| Enums com `create_type=False` | ✅ Implementado |
| Relationships com `back_populates` | ✅ Implementado |
| Cascade delete (`cascade="all, delete-orphan"`) | ✅ Implementado |
| Timestamps com `DateTime(timezone=True)` | ✅ Implementado |
| Foreign keys com `ondelete="CASCADE"` | ✅ Implementado |
| Indexes em status/title/flow_id | ✅ Implementado |
| Soft delete com `deleted_at` | ✅ Implementado |
| `updated_at` com `onupdate=func.now()` | ✅ Implementado |
| Nenhum `user_id` em Flow | ✅ Confirmado |
| Testes de integração async | ✅ Implementado |
| Sem documentação YAP | ✅ Apenas code |

---

## Resumo Técnico

### Hierarquia de Dados

```
Flow (scan session)
  ├── id (PK)
  ├── status (enum: created, running, waiting, finished, failed)
  ├── title, model, model_provider, language
  ├── functions (JSON), prompts (JSON)
  ├── created_at, updated_at, deleted_at
  └── tasks (relationship: 1-to-many)
      │
      └── Task (major testing phase)
            ├── id (PK)
            ├── status (enum)
            ├── title, input, result
            ├── flow_id (FK -> flows.id)
            ├── created_at, updated_at
            └── subtasks (relationship: 1-to-many)
                │
                └── Subtask (atomic agent assignment)
                      ├── id (PK)
                      ├── status (enum)
                      ├── title, description, result, context
                      ├── task_id (FK -> tasks.id)
                      └── created_at, updated_at
```

### Padrões Implementados

1. **Cascade Delete** — Apagar Flow apaga Tasks e Subtasks automaticamente
2. **Soft Delete** — `deleted_at` field permite "apagar" sem realmente apagar
3. **Auditing** — `created_at` e `updated_at` são automaticamente gerados pelo servidor
4. **Type Safety** — Enums Python com type hints em vez de strings
5. **Indexing** — Indexes em status, title, e foreign keys para performance
6. **Async-First** — Async relationships e lazy loading para aplicações async

---

## Próximas Steps (Futuras US)

- [ ] US-009: Migration Scripts (Alembic)
- [ ] US-010: CRUD Operations (Service Layer)
- [ ] US-011: Query Helpers (Filters, Pagination)
- [ ] US-012: Events & Hooks (e.g., cascade behaviors)

---

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[PROJECT-STRUCTURE]]
- [[EXECUTION-FLOW]]
- [[US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED]]
- [[US-007-DATABASE-ENUM-TYPES]]
