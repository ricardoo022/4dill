---
tags: [database]
---

# US-012: Query Functions (CRUD Operations) — Explicacao Detalhada

Este documento explica a camada de queries implementada em `src/pentest/database/queries/flows.py`, `src/pentest/database/queries/tasks.py`, `src/pentest/database/queries/subtasks.py`, `src/pentest/database/queries/containers.py`, `src/pentest/database/queries/toolcalls.py`, `src/pentest/database/queries/msgchains.py`, `src/pentest/database/queries/termlogs.py`, `src/pentest/database/queries/msglogs.py` e os testes de integracao em `tests/integration/database/conftest.py` e `tests/integration/database/test_queries.py`.

---

## Contexto

- A US-012 pede uma API de acesso a dados assíncrona, tipada e separada da orquestracao.
- O runtime atual (flow/task/subtask/container/toolcall/msgchain/termlog/msglog) precisa de CRUD sem expor SQLAlchemy ORM diretamente ao `controller/` e `providers/`.
- Esta camada assume execucao autonoma do scan, sem interacao humana obrigatoria durante o fluxo; estados `WAITING` representam pausa operacional e nao chat com utilizador.
- O objetivo nao e criar uma camada generica para produto futuro; e cobrir apenas o escopo runtime definido em `docs/USER-STORIES.md`.
- O desenho segue o espirito do PentAGI (funcoes por entidade), mas adaptado para Python async + SQLAlchemy 2.0.
- O ganho principal e previsibilidade: API estavel, testes de integracao mais claros e menor acoplamento entre camadas.

---

## Referencia PentAGI (Go)

No PentAGI, as queries sao geradas por SQLC a partir de SQL por entidade. Aqui, o mesmo contrato funcional foi portado como funcoes explicitas em Python assíncrono.

**Diferenca chave:** no Go a tipagem de entrada/saida vem da geracao SQLC; aqui vem da combinacao `Pydantic CreateXxxParams + SQLAlchemy model`.

---

## `CreateFlowParams` e operacoes de Flow (`src/pentest/database/queries/flows.py`)

```python
class CreateFlowParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = "untitled"
    model: str
    model_provider: str
    language: str
    functions: dict = Field(default_factory=dict)
    prompts: dict
    tool_call_id_template: str = ""
    trace_id: str | None = None
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `title` | `str` | `"untitled"` | Titulo visivel do fluxo. |
| `model` | `str` | obrigatorio | Nome do modelo LLM usado no scan. |
| `model_provider` | `str` | obrigatorio | Provider do modelo (ex.: `openai`, `anthropic`). |
| `language` | `str` | obrigatorio | Idioma operacional do fluxo. |
| `functions` | `dict` | `Field(default_factory=dict)` | Mapa de funcoes habilitadas no fluxo; evita mutable default partilhado. |
| `prompts` | `dict` | obrigatorio | Prompt pack efetivo do scan. |
| `tool_call_id_template` | `str` | `""` | Template opcional para IDs de tool-call. |
| `trace_id` | `str \| None` | `None` | Correlacao externa (observabilidade). |

```python
async def get_flow(session: AsyncSession, flow_id: int) -> Flow | None:
    stmt = select(Flow).where(Flow.id == flow_id, Flow.deleted_at.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

```python
async def delete_flow(session: AsyncSession, flow_id: int) -> Flow:
    stmt = (
        update(Flow).where(Flow.id == flow_id).values(deleted_at=datetime.now(UTC)).returning(Flow)
    )
    result = await session.execute(stmt)
    flow = result.scalar_one()
    await session.flush()
    return flow
```

**Porque e assim?**

- `get_flow` e `get_flows` filtram `deleted_at IS NULL` por defeito para garantir semantica de soft delete na API.
- Updates usam `.returning(Flow)` para devolver o estado final em um round-trip.
- `flush()` força sincronizacao da sessao sem obrigar commit dentro da query function.

---

## `CreateTaskParams` e operacoes de Task (`src/pentest/database/queries/tasks.py`)

```python
class CreateTaskParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: TaskStatus
    title: str
    input: str
    flow_id: int
```

| Campo | Tipo | Explicacao |
|---|---|---|
| `status` | `TaskStatus` | Estado inicial da task. |
| `title` | `str` | Nome da fase de trabalho. |
| `input` | `str` | Input operacional da task. |
| `flow_id` | `int` | FK para `flows.id`. |

```python
async def get_flow_tasks(session: AsyncSession, flow_id: int) -> list[Task]:
    stmt = select(Task).where(Task.flow_id == flow_id).order_by(Task.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

Esta ordenacao ascendente e exigida pela US para manter reproducibilidade da execucao.

---

## `CreateSubtaskParams` e bulk create (`src/pentest/database/queries/subtasks.py`)

```python
class CreateSubtaskParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: SubtaskStatus
    title: str
    description: str
    context: str = ""
    task_id: int
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `status` | `SubtaskStatus` | obrigatorio | Estado da unidade atomica. |
| `title` | `str` | obrigatorio | Nome curto da subtask. |
| `description` | `str` | obrigatorio | Instrucao detalhada. |
| `context` | `str` | `""` | Contexto adicional para execucao. |
| `task_id` | `int` | obrigatorio | FK para `tasks.id`. |

```python
async def create_subtasks(
    session: AsyncSession, params_list: list[CreateSubtaskParams]
) -> list[Subtask]:
    subtasks = [Subtask(**params.model_dump()) for params in params_list]
    session.add_all(subtasks)
    await session.flush()
    for subtask in subtasks:
        await session.refresh(subtask)
    return subtasks
```

Passos:
1. Converte parametros tipados para instancias ORM.
2. Usa `add_all()` para envio em lote.
3. Faz `flush()` unico para persistir IDs.
4. `refresh()` de cada item para garantir estado completo retornado.

---

## `CreateContainerParams` e updates granulares (`src/pentest/database/queries/containers.py`)

```python
class CreateContainerParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: ContainerType = ContainerType.PRIMARY
    name: str | None = None
    image: str
    status: ContainerStatus = ContainerStatus.STARTING
    local_id: str | None = None
    local_dir: str | None = None
    flow_id: int
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `type` | `ContainerType` | `PRIMARY` | Tipo de container runtime. |
| `name` | `str \| None` | `None` | Nome human-readable opcional. |
| `image` | `str` | obrigatorio | Imagem Docker usada. |
| `status` | `ContainerStatus` | `STARTING` | Estado inicial do ciclo de vida. |
| `local_id` | `str \| None` | `None` | ID local do daemon Docker. |
| `local_dir` | `str \| None` | `None` | Diretoria local montada, quando existe. |
| `flow_id` | `int` | obrigatorio | FK para flow. |

```python
async def update_container_status_local_id(
    session: AsyncSession, container_id: int, status: ContainerStatus, local_id: str
) -> Container:
    stmt = (
        update(Container)
        .where(Container.id == container_id)
        .values(status=status, local_id=local_id)
        .returning(Container)
    )
```

O modulo separa updates por responsabilidade (`status`, `status+local_id`, `image`) para manter chamadas explicitas na camada de orquestracao.

---

## `CreateToolcallParams` e auditoria de execucao (`src/pentest/database/queries/toolcalls.py`)

```python
class CreateToolcallParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: str
    status: ToolcallStatus = ToolcallStatus.RECEIVED
    name: str
    args: dict = Field(default_factory=dict)
    flow_id: int
    task_id: int | None = None
    subtask_id: int | None = None
```

| Campo | Tipo | Default | Explicacao |
|---|---|---|---|
| `call_id` | `str` | obrigatorio | ID logico da chamada de ferramenta. |
| `status` | `ToolcallStatus` | `RECEIVED` | Estado inicial de rastreio. |
| `name` | `str` | obrigatorio | Nome da ferramenta executada. |
| `args` | `dict` | `Field(default_factory=dict)` | Argumentos serializados da chamada. |
| `flow_id` | `int` | obrigatorio | FK de escopo. |
| `task_id` | `int \| None` | `None` | FK opcional para task. |
| `subtask_id` | `int \| None` | `None` | FK opcional para subtask. |

As funcoes `update_toolcall_finished_result` e `update_toolcall_failed_result` padronizam o fecho de execucao com `status`, `result` e `duration_seconds` no mesmo update.

---

## `CreateMsgchainParams` e acumulacao atomica (`src/pentest/database/queries/msgchains.py`)

```python
class CreateMsgchainParams(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: MsgchainType = MsgchainType.PRIMARY_AGENT
    model: str
    model_provider: str
    usage_in: int = 0
    usage_out: int = 0
    usage_cache_in: int = 0
    usage_cache_out: int = 0
    usage_cost_in: float = 0.0
    usage_cost_out: float = 0.0
    duration_seconds: float = 0.0
    chain: list = Field(default_factory=list)
    flow_id: int
    task_id: int | None = None
    subtask_id: int | None = None
```

```python
async def update_msgchain_usage(
    session: AsyncSession, msgchain_id: int, usage_in: int, usage_out: int
) -> Msgchain:
    stmt = (
        update(Msgchain)
        .where(Msgchain.id == msgchain_id)
        .values(
            usage_in=Msgchain.usage_in + usage_in,
            usage_out=Msgchain.usage_out + usage_out,
        )
        .returning(Msgchain)
    )
```

**Porque e assim?**

- A soma acontece no lado SQL (`campo = campo + delta`) para evitar race de read-modify-write na aplicacao.
- `chain` usa `default_factory=list` para nao partilhar referencia mutavel entre instancias.

---

## `CreateTermlogParams` e `CreateMsglogParams` (`src/pentest/database/queries/termlogs.py`, `src/pentest/database/queries/msglogs.py`)

```python
class CreateTermlogParams(BaseModel):
    type: TermlogType
    text: str
    container_id: int
    flow_id: int
    task_id: int | None = None
    subtask_id: int | None = None
```

```python
class CreateMsglogParams(BaseModel):
    type: MsglogType
    message: str
    result: str = ""
    result_format: MsglogResultFormat = MsglogResultFormat.PLAIN
    flow_id: int
    task_id: int | None = None
    subtask_id: int | None = None
```

Estas entidades cobrem observabilidade runtime:
- `termlogs`: output de terminal por flow/container.
- `msglogs`: mensagens operacionais + resultado estruturado.

---

## Fixture de schema para integracao (`tests/integration/database/conftest.py`)

```python
@pytest.fixture(scope="module")
def db_schema():
    alembic_cfg = _get_alembic_config()
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    _downgrade_base_if_present(alembic_cfg)
    _force_reset_runtime_schema()

    command.upgrade(alembic_cfg, "head")
    yield

    _downgrade_base_if_present(alembic_cfg)
    _force_reset_runtime_schema()
```

Fluxo da fixture:
1. Normaliza URL da BD de teste.
2. Tenta downgrade seguro se houver estado Alembic.
3. Faz reset forzado de schema runtime (tabelas, tipos, funcao trigger).
4. Sobe migracoes ate `head`.
5. No teardown, repete limpeza para isolamento entre modulos.

---

## Exemplo Completo

Caso: Orquestrador cria flow, task e subtasks; depois marca resultados.

```
Input (controller)
  -> CreateFlowParams(model="gpt-4", ...)
  -> CreateTaskParams(status=CREATED, ...)
  -> [CreateSubtaskParams(...), ...]

Persistencia
  -> create_flow(session, params)
  -> create_task(session, params)
  -> create_subtasks(session, params_list)

Execucao
  -> update_subtask_status(..., RUNNING)
  -> update_subtask_result(..., "ok")
  -> update_task_status(..., FINISHED)

Output
  -> get_flow_tasks(flow_id) ordenado por created_at ASC
  -> get_task_subtasks(task_id) ordenado por created_at ASC
```

Diagrama de controlo:

```
Controller
   |
   v
queries/*.py (API tipada)
   |
   v
AsyncSession.execute(select/update/delete)
   |
   v
PostgreSQL
```

---

## Testes de Integracao (`tests/integration/database/test_queries.py`)

Cobertura validada contra a US:

- CRUD de todas as entidades runtime.
- `get_flow_tasks` ordenado e caso vazio.
- Soft delete em flow e filtro por `deleted_at IS NULL`.
- Bulk create de 5 subtasks.
- `IntegrityError` para `local_id` duplicado em containers.
- Acumulacao de usage em msgchain (`0 + 100 + 200 = 300`).
- Rollback transacional quando ocorre erro de FK.

Comando principal:

```bash
pytest tests/integration/database/test_queries.py -v
```

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/database/queries/flows.py` | CRUD de Flow + soft delete. |
| `src/pentest/database/queries/tasks.py` | CRUD de Task + listagem ordenada por flow. |
| `src/pentest/database/queries/subtasks.py` | CRUD de Subtask + bulk create. |
| `src/pentest/database/queries/containers.py` | CRUD de Container + updates granulares. |
| `src/pentest/database/queries/toolcalls.py` | Auditoria de tool-calls e fecho de status. |
| `src/pentest/database/queries/msgchains.py` | Historico LLM e acumulacao de usage. |
| `src/pentest/database/queries/termlogs.py` | Logs de terminal por flow. |
| `src/pentest/database/queries/msglogs.py` | Logs operacionais por flow. |
| `tests/integration/database/conftest.py` | Setup/teardown robusto de schema para integracao. |
| `tests/integration/database/test_queries.py` | Verificacao end-to-end dos contratos de query. |

---

## Questoes Frequentes

### P: Porque as query functions nao fazem `commit()`?

A: Para manter controlo transacional na camada chamadora. A query function persiste (`flush`) e devolve estado; o boundary de commit/rollback fica no fluxo de negocio.

### P: Porque usar `returning(Model)` nos updates?

A: Evita round-trip extra (`UPDATE` + `SELECT`) e devolve o estado final imediatamente.

### P: Porque filtrar soft delete so em Flow?

A: Porque o contrato da US define soft delete explicitamente para `flows`; outras entidades mantem comportamento de delecao/consulta conforme o modelo atual.

---

## Related Notes

- [Docs Home](../../README.md)
- [[USER-STORIES]]
- [[DATABASE-SCHEMA]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Database/US-011-ALEMBIC-MIGRATIONS-EXPLAINED]] 
