---
tags: [database]
---

# US-007: Enum Types — Explicacao Detalhada

Este documento explica linha a linha o ficheiro `src/pentest/database/enums.py`, que define os 10 tipos enum PostgreSQL e suas correspondentes classes Python para o sistema de rastreamento de fluxos, tarefas e subtarefas no SecureDev PentestAI.

---

## Contexto

O PentAGI usa PostgreSQL com tipos ENUM para garantir que os campos de status sejam type-safe e consistentes entre C++, Go e Python. Os enums controlam o ciclo de vida de:

- **Fluxos** (scans)
- **Tarefas** (fases de teste)
- **Subtarefas** (atribuicoes atomicas a agentes)
- **Containers** (Kali Linux instances)
- **Tool calls** (execucoes de ferramentas)
- **Cadeias de mensagens** (tipos de agentes LLM)
- **Logs** (stdin/stdout/stderr e tipos de mensagens)

Em Python, precisamos destas enums para:

1. **Type hints** — `status: FlowStatus` em vez de `status: str` (ambiguo)
2. **Validacao** — casting `FlowStatus("invalid")` gera `ValueError`
3. **Serializacao JSON** — `json.dumps(FlowStatus.CREATED.value)` = `"created"` (native)
4. **SQLAlchemy** — binding com PostgreSQL `ENUM` types para queries type-safe
5. **Alembic migrations** — Alembic pode validar valores ao fazer deploy

---

## Imports (linhas 1-9)

```python
"""PostgreSQL enum types for SecureDev PentestAI.

All enums inherit from (str, Enum) for native JSON string serialization.
Enum string values are lowercase and match PostgreSQL enum definitions exactly.
"""

from enum import Enum as PyEnum

from sqlalchemy import Enum as SQLEnum
```

| Import | Para que serve |
|---|---|
| `Enum as PyEnum` | Classe base standard Python 3.11+. Usamos alias para nao conflituar com `Enum` do SQLAlchemy |
| `Enum as SQLEnum` | Classe SQLAlchemy que wrapper um Python enum para queries ORM type-safe |

**Nota importante**: Importamos ambas como **aliases** porque ambas se chamam `Enum` — sem os aliases haveria confusao.

---

## Padrão Base: `(str, Enum)`

Todas as 10 classes enum **herdam de `(str, Enum)`** em vez do standard `Enum`. Isto e crucial:

```python
# ERRADO — nao e string serializable:
class FlowStatus(Enum):
    CREATED = "created"  # Sera FlowStatus.CREATED, nao "created"

json.dumps(FlowStatus.CREATED)  # TypeError: Object of type FlowStatus is not JSON serializable

# CORRETO — e string, JSON-friendly:
class FlowStatus(str, Enum):
    CREATED = "created"  # E ambas FlowStatus.CREATED E uma string "created"

json.dumps(FlowStatus.CREATED.value)  # "created" (string pura)
# Mais ainda:
json.dumps(FlowStatus.CREATED)  # "created" — Python serializa automaticamente!
```

O `(str, Enum)` mixin faz com que **cada membro seja uma subclasse de `str`**. Isto significa:

- `str(FlowStatus.CREATED)` = `"created"`
- `json.dumps(FlowStatus.CREATED)` = `"created"` (sem precisar `.value`)
- `FlowStatus("created")` = `FlowStatus.CREATED` (conversao bidirecional)
- Comparacoes: `FlowStatus.CREATED == "created"` = `True` (!)

---

## Os 10 Enums PostgreSQL

Cada enum corresponde a uma coluna `status` em uma tabela (ou tipo especifico de dados). Todos definidos em linhas 13-150.

### 1. **FlowStatus** (linhas 13-19)

```python
class FlowStatus(str, PyEnum):
    """Flow (scan session) status enumeration."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"
    FAILED = "failed"
```

Representa o ciclo de vida de um **scan completo** (flow). Tabela `flows` em PostgreSQL.

| Status | Significado |
|---|---|
| `CREATED` | O scan foi registado mas ainda nao comecou |
| `RUNNING` | O scan esta em progresso (agentes a trabalhar) |
| `WAITING` | O scan esta pausado por motivo operacional (ex: retoma via MCP, dependencia externa, recuperacao apos interrupcao) |
| `FINISHED` | O scan completou com sucesso |
| `FAILED` | O scan terminou com erro |

**Source**: PentAGI `initial_state.sql` linha 109

---

### 2. **TaskStatus** (linhas 22-28)

```python
class TaskStatus(str, PyEnum):
    """Task (major testing phase) status enumeration."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"
    FAILED = "failed"
```

Representa o ciclo de vida de uma **tarefa principal** (fase de teste, ex: "Phase 1: Reconnaissance"). Tabela `tasks` em PostgreSQL.

E **identico** a `FlowStatus` — uma tarefa tem os mesmos estados que um scan. Isto e intencional: simplifca a logica de state machines (toda coisa com "fases" tem 5 estados).

**Source**: PentAGI `initial_state.sql` linha 131

---

### 3. **SubtaskStatus** (linhas 31-37)

```python
class SubtaskStatus(str, PyEnum):
    """Subtask (atomic agent assignment) status enumeration."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"
    FAILED = "failed"
```

Representa o ciclo de vida de uma **subtarefa** (atribuicao atomica a um agente, ex: "Generate attack plan for web app"). Tabela `subtasks`.

Idem — 5 estados padrao.

**Source**: PentAGI `initial_state.sql` linha 155

---

### 4. **ContainerType** (linhas 40-45)

```python
class ContainerType(str, PyEnum):
    """Docker container type enumeration."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
```

Tipo de container Docker para execucao de ferramentas. Tabela `containers` coluna `type`.

- `PRIMARY` — O container "master" onde todas as ferramentas correm por padrao (Kali Linux)
- `SECONDARY` — Containers "workers" adicionais para paralelizacao (menos comum)

**Source**: PentAGI `initial_state.sql` linha 174

---

### 5. **ContainerStatus** (linhas 48-55)

```python
class ContainerStatus(str, PyEnum):
    """Docker container status enumeration."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    DELETED = "deleted"
    FAILED = "failed"
```

Ciclo de vida de um container Docker. Tabela `containers` coluna `status`.

| Status | Significado |
|---|---|
| `STARTING` | `docker run` foi chamado, container esta a arrancar |
| `RUNNING` | Container esta vivo e pronto para receber comandos |
| `STOPPED` | `docker stop` foi chamado ou container terminou naturalmente |
| `DELETED` | `docker rm` foi chamado, container e recurso liberado |
| `FAILED` | Container falhou (ex: OOM, crash) |

**Source**: PentAGI `initial_state.sql` linha 193

---

### 6. **ToolcallStatus** (linhas 58-64)

```python
class ToolcallStatus(str, PyEnum):
    """Tool call execution status enumeration."""

    RECEIVED = "received"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
```

Ciclo de vida da **execucao de uma ferramenta individual** (ex: um comando `nmap` ou `sqlmap`). Tabela `toolcalls`.

- `RECEIVED` — O LLM pediu para executar uma tool, foi registada na DB mas ainda nao comecou
- `RUNNING` — Executando...
- `FINISHED` — Completou com sucesso
- `FAILED` — Falhou (exit code != 0 ou timeout)

**Source**: PentAGI `initial_state.sql` linha 216

---

### 7. **MsgchainType** (linhas 67-82)

```python
class MsgchainType(str, PyEnum):
    """LLM message chain type (agent role) enumeration."""

    PRIMARY_AGENT = "primary_agent"
    REPORTER = "reporter"
    GENERATOR = "generator"
    REFINER = "refiner"
    REFLECTOR = "reflector"
    ENRICHER = "enricher"
    ADVISER = "adviser"
    CODER = "coder"
    MEMORIST = "memorist"
    SEARCHER = "searcher"
    INSTALLER = "installer"
    PENTESTER = "pentester"
    SUMMARIZER = "summarizer"
    TOOL_CALL_FIXER = "tool_call_fixer"
```

**14 valores** — sao os agentes e auxiliares actualmente no scope do LusitAI. Cada mensagem LLM (input/output do LLM) e rotulada com o seu tipo de agente. O valor `assistant` do PentAGI fica fora do scope actual porque nao temos modo chat interactivo neste produto.

| Agente | Funcao | Barrier | Input | Output |
|---|---|---|---|---|
| `primary_agent` | Orquestrador central | `done` | Instrucoes de varredura | "Varredura completa" |
| `generator` | Gera plano de ataque | `subtask_list` | Target + scope | Lista de subtarefas |
| `scanner` | Executa ferramentas (nmap, etc.) | `scan_complete` | Plano | Resultados de scan |
| `coder` | Escreve exploits | `code_ready` | Vulnerabilidade | Codigo exploit |
| `searcher` | Pesquisa em web/DB | `search_done` | Query | Resultados |
| `memorist` | Guarda contexto em vector DB | `memory_done` | Dados | Confirmacao |
| `reporter` | Gera relatorio | `report_ready` | Dados agregados | Relatorio PDF |
| `refiner` | Refina plano (iterativo) | `refine_done` | Plano v1 | Plano v2 |
| `adviser` | Aconselhador | `advise` | Problema | Conselho |
| `reflector` | Reflete sobre resultados | (nenhuma barrier) | Resultados | Reflexao |
| `enricher` | Enriquece dados | (custom) | Dados brutos | Dados enriquecidos |
| `pentester` | Pentester "manual" | (custom) | Contexto | Descobertas |
| `summarizer` | Resume informacao | (custom) | Muita info | Summary |
| `tool_call_fixer` | Repara tool calls ruins | (custom) | Tool call falhada | Tool call corrigida |

**Source**: PentAGI Go models (`msgchain.go`), migration `initial_state.sql` linha 230, com exclusao deliberada do valor `assistant` no schema actual do LusitAI

---

### 8. **TermlogType** (linhas 85-91)

```python
class TermlogType(str, PyEnum):
    """Terminal log type enumeration (stdin/stdout/stderr)."""

    STDIN = "stdin"
    STDOUT = "stdout"
    STDERR = "stderr"
```

Tipo de output de terminal ao executar um comando. Tabela `termlogs`.

Simples: stdin e o que foi enviado para o comando, stdout e stderr sao os seus outputs. Usado para guardar historico completo de cada comando executado.

**Source**: PentAGI `initial_state.sql` linha 252

---

### 9. **MsglogType** (linhas 94-106)

```python
class MsglogType(str, PyEnum):
    """Message log type (agent message kind) enumeration."""

    THOUGHTS = "thoughts"
    BROWSER = "browser"
    TERMINAL = "terminal"
    FILE = "file"
    SEARCH = "search"
    ADVICE = "advice"
    INPUT = "input"
    DONE = "done"
    ANSWER = "answer"
    REPORT = "report"
```

**10 valores** — tipos de mensagens operacionais e de auditoria usados no fluxo autonomo actual. O valor `ask` do PentAGI fica fora do scope actual porque implica interaccao ou prompt conversacional que nao faz parte do produto actual.

| Tipo | De quem | Significado |
|---|---|---|
| `THOUGHTS` | Qualquer agente | Pensamento/raciocinio interno do LLM (ex: "Vou primeiro fazer um nmap...") |
| `BROWSER` | Scanner | Visitei uma URL, aqui esta o HTML/screenshots |
| `TERMINAL` | Scanner | Executei um comando terminal, resultado: ... |
| `FILE` | Coder | Criei/modifiquei um ficheiro |
| `SEARCH` | Searcher | Pesquisei, encontrei: ... |
| `ADVICE` | Adviser | Conselho: ... |
| `INPUT` | Qualquer | Input recebido via MCP ou contexto de arranque do fluxo |
| `DONE` | Qualquer | Sinalizador de barrier: "Terminei" |
| `ANSWER` | Qualquer | Resposta a uma pergunta |
| `REPORT` | Reporter | Relatorio final |

**Source**: PentAGI `initial_state.sql` linha 266, com exclusao deliberada do valor `ask` no schema actual do LusitAI

---

### 10. **MsglogResultFormat** (linhas 109-114)

```python
class MsglogResultFormat(str, PyEnum):
    """Message log result format enumeration."""

    TERMINAL = "terminal"
    PLAIN = "plain"
    MARKDOWN = "markdown"
```

**3 valores** — formato em que um resultado e apresentado. Tabela `msglogs` coluna `result_format`.

- `TERMINAL` — Output bruto de terminal (ex: nmap output)
- `PLAIN` — Texto plano simples
- `MARKDOWN` — Formatted markdown (para outputs complexos)

Utilizado para UI/apresentacao — saber como renderizar cada mensagem.

**Source**: PentAGI migration `20241222_171335_msglog_result_format.sql`

---

## SQLAlchemy Type Wrappers (linhas 117-150)

```python
# SQLAlchemy type wrappers for use in SQLAlchemy column definitions.
# The `create_type=False` parameter tells Alembic that these types are
# created separately in migrations (via CREATE TYPE commands), not automatically.

FlowStatusType = SQLEnum(FlowStatus, name="flow_status", create_type=False)
TaskStatusType = SQLEnum(TaskStatus, name="task_status", create_type=False)
SubtaskStatusType = SQLEnum(SubtaskStatus, name="subtask_status", create_type=False)
ContainerTypeType = SQLEnum(ContainerType, name="container_type", create_type=False)
ContainerStatusType = SQLEnum(ContainerStatus, name="container_status", create_type=False)
ToolcallStatusType = SQLEnum(ToolcallStatus, name="toolcall_status", create_type=False)
MsgchainTypeType = SQLEnum(MsgchainType, name="msgchain_type", create_type=False)
TermlogTypeType = SQLEnum(TermlogType, name="termlog_type", create_type=False)
MsglogTypeType = SQLEnum(MsglogType, name="msglog_type", create_type=False)
MsglogResultFormatType = SQLEnum(MsglogResultFormat, name="msglog_result_format", create_type=False)
```

Sao **wrappers SQLAlchemy** para usar em definicoes de colunas ORM. Exemplo de como serao usados em `models.py`:

```python
from pentest.database.enums import FlowStatusType, SubtaskStatusType

class Flow(Base):
    __tablename__ = "flows"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # ...

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[TaskStatus] = mapped_column(TaskStatusType, default=TaskStatus.CREATED)
    # ...

class Subtask(Base):
    __tablename__ = "subtasks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[SubtaskStatus] = mapped_column(SubtaskStatusType, default=SubtaskStatus.CREATED)
    # ...
```

### Detalhe: `create_type=False`

Por que `create_type=False`? Porque:

1. **Alembic cria os types uma unica vez** em migracao inicial (e.g., `migrations/versions/001_initial.py`)
   ```sql
   CREATE TYPE flow_status AS ENUM ('created', 'running', 'waiting', 'finished', 'failed');
   ```

2. Se `create_type=True` (default), SQLAlchemy tentaria criar o type **toda** a vez que inicia a aplicacao — erro se ja existe

3. Ao usar `create_type=False`, SQLAlchemy assume que o type ja existe em PostgreSQL (porque a migracao Alembic o criou antes)

Este e o pattern "correto" em producao com Alembic + PostgreSQL ENUM.

### Padrão de Nomes: `CamelCaseType` → `snake_case`

Repara no padrão:

```python
FlowStatusType        → name="flow_status"       # SQL type name
TaskStatusType        → name="task_status"
MsgchainTypeType      → name="msgchain_type"     # "Type" removido, nao repetido
MsglogResultFormatType → name="msglog_result_format"
```

E simple: conversao CamelCase → snake_case, sem o sufixo `Type` (que e so Python, nao SQL).

---

## Exemplo: Fluxo Completo de um Enum

### 1. Definicao Python

```python
class FlowStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
```

### 2. Modelo SQLAlchemy

```python
from pentest.database.enums import FlowStatusType

class Flow(Base):
    __tablename__ = "flows"
    status: Mapped[FlowStatus] = mapped_column(FlowStatusType, default=FlowStatus.CREATED)
```

### 3. Migracao Alembic

```python
# migrations/versions/001_initial.py
def upgrade():
    op.execute("""
        CREATE TYPE flow_status AS ENUM (
            'created', 'running', 'waiting', 'finished', 'failed'
        )
    """)
    op.create_table(
        'flows',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.Enum('created', 'running', ..., name='flow_status'), ...),
        ...
    )
```

### 4. Uso em Queries

```python
from pentest.database.enums import FlowStatus

# Criar novo flow
flow = Flow(status=FlowStatus.CREATED)
await session.add(flow)
await session.commit()

# Query: encontrar todos os flows em progresso
result = await session.execute(
    select(Flow).where(Flow.status == FlowStatus.RUNNING)
)
flows = result.scalars().all()

# Atualizar status
flow.status = FlowStatus.FINISHED
await session.commit()

# JSON API serialization
return {
    "id": flow.id,
    "status": flow.status.value,  # "finished" (string)
}
```

### 5. Type Safety

```python
# IDE/mypy valida isto:
if flow.status == FlowStatus.RUNNING:
    ...

# Mas rejeita isto:
if flow.status == "running":  # mypy: error (type mismatch)
    ...

# E isto gera ValueError em runtime:
status = FlowStatus("invalid")  # ValueError: 'invalid' is not a valid FlowStatus
```

---

## Resumo das Decisões de Design

| Decisao | Razao | Impacto |
|---|---|---|
| `(str, Enum)` em vez de `Enum` | JSON serializacao nativa | Sem `.value` necessario em dumps() |
| 10 enums em 1 ficheiro | Coesao — todos relacionados DB | Facil de importar, manter junto |
| Valores lowercase | Match com PentAGI SQL | Compatibilidade migracoes existentes |
| `create_type=False` | Alembic controla tipos | Nao recreamos types desnecessariamente |
| SQLAlchemy wrappers | Type hints em models | IDE autocomplete, mypy validacao |

---

## Teste: Como Validar

O ficheiro `tests/unit/database/test_enums.py` testa:

1. **Member counts** — MsgchainType tem exatamente 15, MsglogType tem 11
2. **String serialization** — `FlowStatus.CREATED.value == "created"`
3. **Deserialization** — `FlowStatus("created") == FlowStatus.CREATED`
4. **Invalid values** — `FlowStatus("invalid")` lanca `ValueError`
5. **JSON roundtrip** — `json.dumps(enum.value)` e `json.loads()` funcionam

```bash
pytest tests/unit/database/test_enums.py -v
# Output: 41 passed
```

---

## Migracao: Como Criaremos os Types em PostgreSQL

Em US-011 (Alembic migrations), criaremos migracao que:

1. Define cada `CREATE TYPE` enum
2. Cria tabelas (flows, tasks, subtasks, containers, etc.) com colunas ENUM
3. Usa `create_type=False` para nao conflituar com SQLAlchemy

Exemplo:

```python
# alembic/versions/001_initial.py
def upgrade():
    # Step 1: Create all enum types
    op.execute("""
        CREATE TYPE flow_status AS ENUM (
            'created', 'running', 'waiting', 'finished', 'failed'
        )
    """)
    op.execute("""
        CREATE TYPE task_status AS ENUM (
            'created', 'running', 'waiting', 'finished', 'failed'
        )
    """)
    # ... more enum types ...

    # Step 2: Create tables with ENUM columns
    op.create_table(
        'flows',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('status', sa.Enum(..., name='flow_status'), nullable=False, server_default='created'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    # ... more tables ...
```

---

## Proximas Epics que Usam Estes Enums

- **US-008**: Modelos SQLAlchemy (`Flow`, `Task`, `Subtask`) — usam `FlowStatusType`, `TaskStatusType`, `SubtaskStatusType`
- **US-009**: Modelos de containers — usam `ContainerTypeType`, `ContainerStatusType`
- **US-010**: Modelos de logs — usam `TermlogTypeType`, `MsglogTypeType`, `MsglogResultFormatType`
- **US-011**: Alembic migrations — cria os `CREATE TYPE` SQL baseado nestas definicoes Python

---

## Conclusao

`src/pentest/database/enums.py` e o **single source of truth** para todos os tipos categoricos do sistema. Toda aplicacao Python (models, queries, APIs, testes) importa deste ficheiro. Toda migracao Alembic valida contra estas definicoes.

O design `(str, Enum)` garante que:
- ✅ Python type hints funcionam
- ✅ JSON serialization e nativa
- ✅ Queries SQLAlchemy sao type-safe
- ✅ Migraces Alembic sao deterministas (nao recreamos types)

E pronto para o proximo passo: **US-008 — Core SQLAlchemy Models**.

---

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[PROJECT-STRUCTURE]]
- [[US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED]]
- [[US-008-CORE-DB-MODELS]]
