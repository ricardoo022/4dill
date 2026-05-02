---
tags: [database]
---

# US-009: Supporting SQLAlchemy Models (containers, toolcalls, msgchains, termlogs, msglogs) — Explicacao Detalhada

Este documento explica os modelos SQLAlchemy implementados em `src/pentest/database/models.py` que dao suporte ao fluxo de execucao runtime: containers Docker, historico de tool calls, chains deLLM, logs de terminal e eventos operacionais.

---

## Contexto

O US-008 implements as tabelas core da hierarquia (Flow, Task, Subtask). O US-009 adiciona as tabelas de suporte que permitem ao motor autonomous operar, rastrear e recuperar o estado durante um scan:

- **containers**: controla os containers Docker criados por cada flow. Cada container tem um `flow_id` que permite encontrar todos os containers de um scan.
- **toolcalls**: log de cada tool chamada executada pelo agente. Inclui nome, args, resultado e tempo de execucao.
- **msgchains**: armazena a conversacao completa LLM (chain de mensagens) como JSON. Permite recuperacao e audit.
- **termlogs**: captura output stdin/stdout/stderr de cada container. Inclui FK directo para flow/task/subtask para queries rapidas sem JOIN.
- **msglogs**: eventos operacionais emitidos pelo motor (logs, answers, reports). Suporta formatacao de resultado.

Estas tabelas sao runtime/audit persistence, NAO sao modelo de chat interactivo. O schema NAO inclui variantes assistant/HITL que foram removidas em US-007.

---

## `_random_md5_name` (linhas 48-51)

Funcao geradora de nomes aleatorios para containers. Usada como default Callable no SQLAlchemy.

```python
def _random_md5_name() -> str:
    """Generate a random md5-like container name token."""

    return hashlib.md5(uuid4().bytes, usedforsecurity=False).hexdigest()
```

| Linha(s) | Explicacao |
|---|---|
| 48-51 | Funcao sem parametros que retorna uma string de 32 caracteres hexadecimais (formato md5). Usada por `Container.name` como default. Gera nome unico para cada container sem necessidade de persistir antes. |

**Porque e assim?**: Um hash md5 de um UUID aleatorio e suficientemente unico para nomes de container, mas mais curto que um UUID completo e mais legivel que bytes raw.

---

## `Container` (linhas 217-264)

Modelo que representa um container Docker associado a um scan (Flow).

```python
class Container(Base):
    """Docker container tracked for runtime execution and recovery."""

    __tablename__ = "containers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[ContainerType] = mapped_column(
        ContainerTypeType,
        server_default=text("'primary'"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, default=_random_md5_name, nullable=False)
    image: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContainerStatus] = mapped_column(
        ContainerStatusType,
        server_default=text("'starting'"),
        nullable=False,
    )
    local_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    local_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    flow: Mapped[Flow] = relationship("Flow", back_populates="containers", lazy="selectin")
    termlogs: Mapped[list["Termlog"]] = relationship(
        "Termlog",
        back_populates="container",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_containers_type", "type"),
        Index("ix_containers_name", "name"),
        Index("ix_containers_status", "status"),
        Index("ix_containers_flow_id", "flow_id"),
    )
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `id` | BigInteger | auto-increment | PK sequencial |
| `type` | ContainerType | `'primary'` | Tipo de container (primary/secondary) |
| `name` | Text | `_random_md5_name()` | Nome unico gerado automaticamente |
| `image` | Text | - | Nome da imagem Docker |
| `status` | ContainerStatus | `'starting'` | Estado actual do container |
| `local_id` | Text (nullable) | None | ID real do container no Docker daemon |
| `local_dir` | Text (nullable) | None | Directorio de trabalho no host |
| `flow_id` | BigInteger (FK) | - | FK para flows (cascade delete) |
| `created_at` | DateTime | `now()` | Timestamp de criacao |
| `updated_at` | DateTime | `now()` | Auto-update em mudanca |

| Relacionamento | Target | Explicacao |
|---|---|---|
| `flow` | Flow | Access inverse -> flow.containers |
| `termlogs` | list[Termlog] | Cascade delete de termlogs se container for apagado |

| Indice | Colunas | Uso |
|---|---|---|
| `ix_containers_type` | type | Query por tipo |
| `ix_containers_name` | name | Query por nome exacto |
| `ix_containers_status` | status | Query por estado |
| `ix_containers_flow_id` | flow_id | FK directo sem JOIN |

**Notas de design**:
- `local_id` tem CONSTRAINT UNIQUE para evitar duplicados na DB.
- `name` usa Callable default (nao server_default) porque SQLAlchemy precisa avaliar a funcao em Python.
- `passive_deletes=True` na relacao com Termlog indica que o DB cascade resolve, nao o ORM.

---

## `Toolcall` (linhas 267-321)

Modelo que log de cada tool chamada executada por um agente.

```python
class Toolcall(Base):
    """Tool execution history for audit, recovery, and loop detection."""

    __tablename__ = "toolcalls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ToolcallStatus] = mapped_column(
        ToolcallStatusType,
        server_default=text("'received'"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_seconds: Mapped[float] = mapped_column(
        Float, server_default=text("0.0"), nullable=False
    )
    flow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    subtask_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subtasks.id", ondelete="CASCADE"), nullable=True
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

    flow: Mapped[Flow] = relationship("Flow", back_populates="toolcalls", lazy="selectin")
    task: Mapped[Task | None] = relationship("Task", lazy="selectin")
    subtask: Mapped[Subtask | None] = relationship("Subtask", lazy="selectin")

    __table_args__ = (
        Index("ix_toolcalls_call_id", "call_id"),
        Index("ix_toolcalls_status", "status"),
        Index("ix_toolcalls_name", "name"),
        Index("ix_toolcalls_flow_id", "flow_id"),
        Index("ix_toolcalls_task_id", "task_id"),
        Index("ix_toolcalls_subtask_id", "subtask_id"),
        Index("ix_toolcalls_created_at", "created_at"),
        Index("ix_toolcalls_updated_at", "updated_at"),
        Index("ix_toolcalls_flow_id_status", "flow_id", "status"),
        Index("ix_toolcalls_name_status", "name", "status"),
        Index("ix_toolcalls_name_flow_id", "name", "flow_id"),
        Index("ix_toolcalls_status_updated_at", "status", "updated_at"),
    )
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `id` | BigInteger | auto-increment | PK |
| `call_id` | Text | - | ID unico da call (gerado pelo LLM) |
| `status` | ToolcallStatus | `'received'` | Estado: received/running/finished/failed |
| `name` | Text | - | Nome da tool (terminal, browser, etc.) |
| `args` | JSON | `{}` | Argumentos passados a tool |
| `result` | Text | `''` | Output returned pela tool |
| `duration_seconds` | Float | `0.0` | Tempo de execucao em segundos |
| `flow_id` | BigInteger (FK) | - | FK para flows |
| `task_id` | BigInteger (FK, nullable) | None | FK opcional para tasks |
| `subtask_id` | BigInteger (FK, nullable) | None | FK opcional para subtasks |
| `created_at` | DateTime | `now()` | Timestamp |
| `updated_at` | DateTime | `now()` | Auto-update |

| Indice (single) | Indice (composite) |
|---|---|
| `ix_toolcalls_call_id` | `ix_toolcalls_flow_id_status` |
| `ix_toolcalls_status` | `ix_toolcalls_name_status` |
| `ix_toolcalls_name` | `ix_toolcalls_name_flow_id` |
| `ix_toolcalls_flow_id` | `ix_toolcalls_status_updated_at` |
| `ix_toolcalls_task_id` | |
| `ix_toolcalls_subtask_id` | |
| `ix_toolcalls_created_at` | |
| `ix_toolcalls_updated_at` | |

**Notas de design**:
- `task_id` e `subtask_id` sao nullable para permitir toolcalls ao nivel do flow (sem scope granular).
- `duration_seconds` permite calcular custos e detectar loops (20+ chamadas = Adviser intervenha).

---

## `Msgchain` (linhas 324-386)

Modelo que armazena a chain de mensagens completa de uma execucao LLM.

```python
class Msgchain(Base):
    """Internal LLM execution chain stored for runtime recovery and audit."""

    __tablename__ = "msgchains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[MsgchainType] = mapped_column(
        MsgchainTypeType,
        server_default=text("'primary_agent'"),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    usage_in: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    usage_out: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    usage_cache_in: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), nullable=False
    )
    usage_cache_out: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), nullable=False
    )
    usage_cost_in: Mapped[float] = mapped_column(Float, server_default=text("0.0"), nullable=False)
    usage_cost_out: Mapped[float] = mapped_column(Float, server_default=text("0.0"), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(
        Float, server_default=text("0.0"), nullable=False
    )
    chain: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    flow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    subtask_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subtasks.id", ondelete="CASCADE"), nullable=True
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

    flow: Mapped[Flow] = relationship("Flow", back_populates="msgchains", lazy="selectin")
    task: Mapped[Task | None] = relationship("Task", lazy="selectin")
    subtask: Mapped[Subtask | None] = relationship("Subtask", lazy="selectin")

    __table_args__ = (
        Index("ix_msgchains_type", "type"),
        Index("ix_msgchains_flow_id", "flow_id"),
        Index("ix_msgchains_task_id", "task_id"),
        Index("ix_msgchains_subtask_id", "subtask_id"),
        Index("ix_msgchains_created_at", "created_at"),
        Index("ix_msgchains_model_provider", "model_provider"),
        Index("ix_msgchains_model", "model"),
        Index("ix_msgchains_type_flow_id", "type", "flow_id"),
        Index("ix_msgchains_created_at_flow_id", "created_at", "flow_id"),
        Index("ix_msgchains_type_created_at", "type", "created_at"),
        Index("ix_msgchains_type_task_id_subtask_id", "type", "task_id", "subtask_id"),
    )
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `id` | BigInteger | auto-increment | PK |
| `type` | MsgchainType | `'primary_agent'` | Tipo de agent |
| `model` | Text | - | Nome do modelo LLM |
| `model_provider` | Text | - | Provider (anthropic, openai, etc.) |
| `usage_in` | BigInteger | 0 | Tokens de input |
| `usage_out` | BigInteger | 0 | Tokens de output |
| `usage_cache_in` | BigInteger | 0 | Tokens de cache input |
| `usage_cache_out` | BigInteger | 0 | Tokens de cache output |
| `usage_cost_in` | Float | 0.0 | Custo input |
| `usage_cost_out` | Float | 0.0 | Custo output |
| `duration_seconds` | Float | 0.0 | Tempo total de execucao |
| `chain` | JSON | `[]` | Array de mensagens |
| `flow_id` | BigInteger (FK) | - | FK para flows |
| `task_id` | BigInteger (FK, nullable) | None | FK opcional |
| `subtask_id` | BigInteger (FK, nullable) | None | FK opcional |
| `created_at` | DateTime | `now()` | Timestamp |
| `updated_at` | DateTime | `now()` | Auto-update |

**Notas de design**:
- Campos `usage_*` e `duration_seconds` sao todos incluidas desde o inicio (greenfield) conforme US-009 technical notes.
- `chain` e JSON column que store a conversacao completa. Permite recover de falhas.

---

## `Termlog` (linhas 389-426)

Modelo que captura output stdin/stdout/stderr de cada container.

```python
class Termlog(Base):
    """Terminal I/O log captured per container and execution scope."""

    __tablename__ = "termlogs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[TermlogType] = mapped_column(TermlogTypeType, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    container_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("containers.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    subtask_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subtasks.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    container: Mapped[Container] = relationship(
        "Container", back_populates="termlogs", lazy="selectin"
    )
    flow: Mapped[Flow] = relationship("Flow", lazy="selectin")
    task: Mapped[Task | None] = relationship("Task", lazy="selectin")
    subtask: Mapped[Subtask | None] = relationship("Subtask", lazy="selectin")

    __table_args__ = (
        Index("ix_termlogs_type", "type"),
        Index("ix_termlogs_container_id", "container_id"),
        Index("ix_termlogs_flow_id", "flow_id"),
        Index("ix_termlogs_task_id", "task_id"),
        Index("ix_termlogs_subtask_id", "subtask_id"),
    )
```

| Campo | Tipo | Explicacao |
|---|---|---|
| `id` | BigInteger | PK |
| `type` | TermlogType | stdin/stdout/stderr |
| `text` | Texto | Output capturado |
| `container_id` | BigInteger (FK) | FK para containers |
| `flow_id` | BigInteger (FK) | FK directo para flow (sem JOIN) |
| `task_id` | BigInteger (FK, nullable) | FK opcional |
| `subtask_id` | BigInteger (FK, nullable) | FK opcional |
| `created_at` | DateTime | Timestamp |

**Notas de design**:
- `Termlog` tem FK directo para `flow_id`, `task_id` e `subtask_id` alem de `container_id`. Permite queries sem JOIN para performance (PentAGI migration 20260129).

---

## `Msglog` (linhas 429-466)

Modelo que regista eventos operacionais do motor (nao e chat interactivo).

```python
class Msglog(Base):
    """Operational engine log entry for audit and observability."""

    __tablename__ = "msglogs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[MsglogType] = mapped_column(MsglogTypeType, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result_format: Mapped[MsglogResultFormat] = mapped_column(
        MsglogResultFormatType,
        server_default=text("'plain'"),
        nullable=False,
    )
    flow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    subtask_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subtasks.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    flow: Mapped[Flow] = relationship("Flow", back_populates="msglogs", lazy="selectin")
    task: Mapped[Task | None] = relationship("Task", lazy="selectin")
    subtask: Mapped[Subtask | None] = relationship("Subtask", lazy="selectin")

    __table_args__ = (
        Index("ix_msglogs_type", "type"),
        Index("ix_msglogs_flow_id", "flow_id"),
        Index("ix_msglogs_task_id", "task_id"),
        Index("ix_msglogs_subtask_id", "subtask_id"),
        Index("ix_msglogs_result_format", "result_format"),
    )
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|
| `id` | BigInteger | PK |
| `type` | MsglogType | Tipo de mensagem |
| `message` | Texto | Conteudo |
| `result` | Texto | `''` | Resultado (opcional) |
| `result_format` | MsglogResultFormat | `'plain'` | Formato: terminal/plain/markdown |
| `flow_id` | BigInteger (FK) | - | FK para flow |
| `task_id` | BigInteger (FK, nullable) | None | FK opcional |
| `subtask_id` | BigInteger (FK, nullable) | None | FK opcional |
| `created_at` | DateTime | `now()` | Timestamp |

**Notas de design**:
- `Msglog` e runtime/audit persistence, NAO chat interactivo.
- `result_format` included desde o inicio (nao e posterior migration como no PentAGI).
- `result` permite armazenar output formatado (markdown, etc.).

---

## `Flow` relacionamentos suporte (linhas 100-127)

O modelo `Flow` (implementado em US-008) foi extendido com relacionamentos para os modelos US-009:

```python
containers: Mapped[list["Container"]] = relationship(
    "Container",
    back_populates="flow",
    cascade="all, delete-orphan",
    passive_deletes=True,
    lazy="selectin",
)
toolcalls: Mapped[list["Toolcall"]] = relationship(
    "Toolcall",
    back_populates="flow",
    cascade="all, delete-orphan",
    passive_deletes=True,
    lazy="selectin",
)
msgchains: Mapped[list["Msgchain"]] = relationship(
    "Msgchain",
    back_populates="flow",
    cascade="all, delete-orphan",
    passive_deletes=True,
    lazy="selectin",
)
msglogs: Mapped[list["Msglog"]] = relationship(
    "Msglog",
    back_populates="flow",
    cascade="all, delete-orphan",
    passive_deletes=True,
    lazy="selectin",
)
```

| Relacionamento | Explicacao |
|---|---|
| `flow.containers` | Cascade delete automatico |
| `flow.toolcalls` | Cascade delete automatico |
| `flow.msgchains` | Cascade delete automatico |
| `flow.msglogs` | Cascade delete automatico |

**Porque e assim?**: `passive_deletes=True` faz o SQLAlchemy delegar o cascade para o DB (ON DELETE CASCADE), evitando que o ORM faca deletes redundantes que causam warnings.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/database/models.py` | Modelos SQLAlchemy para persistence |
| `tests/unit/database/test_models.py` | Testes de estrutura e metadados |
| `tests/integration/database/test_models.py` | Testes de persistencia real |
| `tests/e2e/database/test_models_e2e.py` | Testes E2E DB com catalog checks |

---

## Referencia PentAGI (Go)

O US-009 e uma traducao directa do schema PentAGI Go:

- **Schema Go**: `pentagi/backend/migrations/sql/20241026_115120_initial_state.sql` linhas 135-283
- **Tabelas**: containers, tool_calls, msg_chains, term_logs, msg_logs

Cada modelo Python corresponde a uma tabela Go com o mesmo nome. As diferencas principais:

1. Python usa SQLAlchemy 2.0 com `Mapped[X]` e `mapped_column()`.
2. Go usa GORM; Python usa async SQLAlchemy com `async_sessionmaker`.
3. Enum types sao representadas por `sqlalchemy.Enum` com wrappers em `database/enums.py`.
4. `Msglog.result_format` incluido desde o inicio (PentAGI tem migration separada).

---

## Ligacoes para Documentacao Relacionada

- **US-008-CORE-DB-MODELS-EXPLAINED.md** — modelos core (Flow, Task, Subtask)
- **US-007-DATABASE-ENUM-TYPES-EXPLAINED.md** — tipos enum usados nos modelos
- **US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED.md** — gestao de conexao DB
- **`src/pentest/database/models.py`** — implementacao
- **`src/pentest/database/enums.py`** — enum definitions
