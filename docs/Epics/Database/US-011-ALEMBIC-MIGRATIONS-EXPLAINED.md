---
tags: [database]
---

# US-011: Alembic Migrations — Explicacao Detalhada

Esta nota documenta as alteracoes em `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial_schema.py`, `tests/integration/database/test_models.py`, `tests/integration/database/test_migrations.py`, `tests/e2e/database/test_migrations_e2e.py` e `tests/unit/database/test_migration_config_us011.py` para tornar o schema do runtime versionado e reproduzivel via Alembic.

---

## Contexto

- Antes desta US, o runtime tinha modelos SQLAlchemy e enums, mas faltava uma migration inicial reproduzivel para criar o schema de ponta a ponta.
- O objectivo foi alinhar o estado real da base de dados com controlo de versao de schema: `upgrade`, `downgrade`, `current` e `check`.
- A US-011 limita o escopo ao runtime actual (flows/tasks/subtasks/containers/toolcalls/msgchains/termlogs/msglogs/vector_store), sem tabelas de plataforma multi-utilizador.
- A implementacao foi feita com foco em idempotencia operacional (`IF NOT EXISTS` para enums/extensao) e rollback limpo no `downgrade()`.
- Os testes foram reorganizados para usar migrations reais em vez de criar schema manualmente, evitando drift entre testes e producao.

---

## `alembic.ini` (`alembic.ini`)

```ini
[alembic]
script_location = alembic
sqlalchemy.url = %(DATABASE_URL)s
```

| Linha(s) | Explicacao |
|---|---|
| 1-3 | Configura Alembic para ler a URL da base de dados via placeholder `%(DATABASE_URL)s`, removendo DSN hardcoded. |

### Porque e assim?

O mesmo ficheiro serve devcontainer, CI e ambientes locais. Centralizar a resolucao na env var elimina dependencias de host fixo (`db`, `localhost`) e evita falhas quando o endpoint muda por ambiente.

---

## Ambiente Alembic Async (`alembic/env.py`)

```python
def _configure_database_url() -> None:
    """Resolve DATABASE_URL and inject it into Alembic config."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for Alembic")

    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    _configure_database_url()
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    _configure_database_url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()
```

| Linha(s) | Explicacao |
|---|---|
| 27-35 | Injecao obrigatoria de `DATABASE_URL` no config runtime do Alembic. |
| 37-53 | Caminho offline com `compare_type` e `compare_server_default` para detetar drift de schema/defaults. |
| 69-82 | Caminho online com `AsyncEngine`, ligacao async e execucao sincronizada de migrations com `run_sync`. |
| 85-88 | Router final offline/online; no modo online arranca com `asyncio.run(...)`. |

Fluxo de routing:

```text
context.is_offline_mode?
├─ yes -> run_migrations_offline()
└─ no  -> asyncio.run(run_migrations_online())
           -> async_engine_from_config
           -> connection.run_sync(do_run_migrations)
```

---

## Migration Inicial (`alembic/versions/001_initial_schema.py`)

```python
revision: str = "001_initial_schema"
down_revision: str | None = None


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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flows_status", "flows", ["status"], unique=False)
    op.create_index("ix_vector_store_metadata_flow_id", "vector_store", [sa.text("(metadata_->>'flow_id')")], unique=False)
    _create_update_trigger_function()
    _create_update_trigger("flows")
    _create_update_trigger("tasks")
    _create_update_trigger("subtasks")
    _create_update_trigger("containers")
    _create_update_trigger("toolcalls")
    _create_update_trigger("msgchains")
```

```python
def _create_enums() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'flow_status') THEN
            CREATE TYPE flow_status AS ENUM ('created', 'running', 'waiting', 'finished', 'failed');
        END IF;
    END
    $$;
    """)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'msglog_result_format') THEN
            CREATE TYPE msglog_result_format AS ENUM ('terminal', 'plain', 'markdown');
        END IF;
    END
    $$;
    """)
```

```python
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
```

```python
def downgrade() -> None:
    _drop_update_trigger("msgchains")
    _drop_update_trigger("toolcalls")
    _drop_update_trigger("containers")
    _drop_update_trigger("subtasks")
    _drop_update_trigger("tasks")
    _drop_update_trigger("flows")
    op.execute("DROP FUNCTION IF EXISTS update_modified_column()")
    # drop indexes, then tables, then enum types
```

| Bloco | Explicacao |
|---|---|
| Revision metadata (17-20) | Define raiz da arvore de migrations (`down_revision=None`). |
| `_create_enums` (23-140) | Cria todos os enums do runtime com guardas `IF NOT EXISTS`, garantindo idempotencia em repeticoes. |
| `upgrade` (173-555) | Cria extensao `vector`, tabelas de runtime, indexes equivalentes aos modelos, funcao de trigger e bindings de trigger. |
| `downgrade` (557-643) | Remove triggers e funcao, apaga indexes, depois tabelas, e finalmente enum types para rollback limpo. |

### Porque e assim?

A ordem no `downgrade` e critica: triggers e funcao precisam sair antes de dropar tabelas referenciadas; indexes devem sair antes das tabelas para evitar erros de dependencia. A remocao de enums no fim garante que nao existem colunas ainda dependentes desses tipos.

---

## Refactor dos testes de modelos (`tests/integration/database/test_models.py`)

```python
def _get_alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


@pytest.fixture(scope="module")
def db_schema():
    alembic_cfg = _get_alembic_config()
    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    with suppress(Exception):
        command.downgrade(alembic_cfg, "base")
    _force_reset_runtime_schema()

    command.upgrade(alembic_cfg, "head")
    yield

    with suppress(Exception):
        command.downgrade(alembic_cfg, "base")
    _force_reset_runtime_schema()
```

| Linha(s) | Explicacao |
|---|---|
| 64-68 | Novo helper centraliza config Alembic para os testes de modelos. |
| 71-97 | Reset forçado do schema (tabelas/tipos/funcao) para garantir baseline deterministico. |
| 100-120 | Fixture `db_schema` passa a usar migrations reais (`downgrade` + `upgrade`) em vez de DDL manual no teste. |

### Porque e assim?

Este refactor elimina drift entre schema de teste e schema migrado. Antes, `test_models.py` recriava tipos/tabelas manualmente; agora o setup valida a mesma cadeia que producao usa (`alembic upgrade head`).

---

## Testes de integracao da migration (`tests/integration/database/test_migrations.py`)

```python
EXPECTED_TABLES = {"flows", "tasks", "subtasks", "containers", "toolcalls", "msgchains", "termlogs", "msglogs", "vector_store"}
EXPECTED_ENUMS = {"flow_status", "task_status", "subtask_status", "container_type", "container_status", "toolcall_status", "msgchain_type", "termlog_type", "msglog_type", "msglog_result_format"}
EXPECTED_TRIGGER_TABLES = {"flows", "tasks", "subtasks", "containers", "toolcalls", "msgchains"}
```

```python
async def test_alembic_upgrade_head_creates_runtime_tables(migrated_db) -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
        )
        existing_tables = {row[0] for row in result.fetchall()}
    assert EXPECTED_TABLES.issubset(existing_tables)


def test_alembic_downgrade_base_drops_runtime_tables(migrated_schema) -> None:
    _run_alembic_downgrade_base()

    async def _assert_tables_dropped() -> None:
        await init_db(TEST_DATABASE_URL, echo=False)
        async with get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )
            existing_tables = {row[0] for row in result.fetchall()}
        await close_db()
        assert EXPECTED_TABLES.isdisjoint(existing_tables)

    asyncio.run(_assert_tables_dropped())


def test_alembic_check_reports_no_pending_migrations() -> None:
    with suppress(Exception):
        _run_alembic_downgrade_base()
    _force_reset_runtime_schema()

    _run_alembic_upgrade_head()
    _run_alembic_check()
```

| Teste | Cobre |
|---|---|
| `test_alembic_upgrade_head_creates_runtime_tables` | `upgrade head` cria schema esperado. |
| `test_alembic_downgrade_base_drops_runtime_tables` | `downgrade base` limpa schema de runtime. |
| `test_alembic_upgrade_head_is_idempotent` | Repeticao de upgrade nao quebra. |
| `test_required_enum_types_exist_after_migration` | Enums esperados no `pg_type`. |
| `test_update_modified_column_function_exists` | Funcao de trigger no `pg_proc`. |
| `test_update_triggers_attached_to_runtime_tables` | Triggers ligados nas tabelas correctas. |
| `test_pgvector_extension_installed_after_migration` | Extensao `vector` ativa. |
| `test_alembic_check_reports_no_pending_migrations` | Schema e metadata sem diff pendente. |

---

## Teste E2E do fluxo real (`tests/e2e/database/test_migrations_e2e.py`)

```python
def test_us011_alembic_real_command_flow() -> None:
    downgrade_initial = _run_alembic("downgrade", "base")
    assert downgrade_initial.returncode == 0, downgrade_initial.stderr

    upgrade = _run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    tables_after_upgrade = _fetch_public_tables()
    assert EXPECTED_RUNTIME_TABLES.issubset(tables_after_upgrade)

    current = _run_alembic("current")
    assert current.returncode == 0, current.stderr
    assert "001_initial_schema" in current.stdout

    check = _run_alembic("check")
    assert check.returncode == 0, check.stderr

    downgrade_final = _run_alembic("downgrade", "base")
    assert downgrade_final.returncode == 0, downgrade_final.stderr

    tables_after_downgrade = _fetch_public_tables()
    assert EXPECTED_RUNTIME_TABLES.isdisjoint(tables_after_downgrade)
```

| Linha(s) | Explicacao |
|---|---|
| 38-48 | Executa comandos Alembic reais via subprocess com `DATABASE_URL` injectada. |
| 51-68 | Confirma estado real do schema via query a `information_schema.tables`. |
| 71-93 | Prova E2E completa: downgrade -> upgrade -> current -> check -> downgrade. |

---

## Testes unitarios de scaffold (`tests/unit/database/test_migration_config_us011.py`)

```python
def test_alembic_ini_uses_database_url_placeholder() -> None:
    alembic_ini = ROOT / "alembic.ini"
    content = alembic_ini.read_text(encoding="utf-8")
    assert "sqlalchemy.url = %(DATABASE_URL)s" in content


def test_alembic_scaffold_exists_for_runtime_migrations() -> None:
    assert (ROOT / "alembic").is_dir()
    assert (ROOT / "alembic" / "env.py").is_file()
    assert (ROOT / "alembic" / "versions").is_dir()
```

| Teste | Objetivo |
|---|---|
| `test_alembic_ini_uses_database_url_placeholder` | Garante configuracao sem URL hardcoded. |
| `test_alembic_scaffold_exists_for_runtime_migrations` | Garante estrutura minima exigida pela AC da US-011. |

---

## Exemplo Completo

```text
Step 1: Estado inicial (DB possivelmente suja)
  -> comando: alembic downgrade base
  -> resultado: schema de runtime removido

Step 2: Provisionamento
  -> comando: alembic upgrade head
  -> resultado: enums + tabelas + indexes + triggers + vector extension

Step 3: Auditoria de versao
  -> comando: alembic current
  -> esperado: 001_initial_schema

Step 4: Verificacao de drift
  -> comando: alembic check
  -> esperado: sem diferencas pendentes

Step 5: Rollback
  -> comando: alembic downgrade base
  -> resultado: schema limpo para novo ciclo
```

```text
┌───────────────┐
│ downgrade base│
└───────┬───────┘
        ↓
┌───────────────┐
│  upgrade head │
└───────┬───────┘
        ↓
┌───────────────┐
│    current    │
└───────┬───────┘
        ↓
┌───────────────┐
│     check     │
└───────┬───────┘
        ↓
┌───────────────┐
│ downgrade base│
└───────────────┘
```

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `alembic.ini` | URL de DB por variavel de ambiente. |
| `alembic/env.py` | Runtime Alembic async com metadata SQLAlchemy e comparacao de drift. |
| `alembic/versions/001_initial_schema.py` | Migration inicial completa do runtime (upgrade/downgrade). |
| `tests/integration/database/test_models.py` | Refactor do setup para bootstrap via Alembic real. |
| `tests/integration/database/test_migrations.py` | Suite de verificacao da US-011 em camada integration. |
| `tests/e2e/database/test_migrations_e2e.py` | Fluxo E2E real com comandos Alembic e prova de estado. |
| `tests/unit/database/test_migration_config_us011.py` | Checks unitarios de scaffold/config minima. |

---

## Questoes Frequentes

### P: Porque existe `_force_reset_runtime_schema()` nos testes se ja temos `downgrade base`?

A: Porque durante iteracao local pode existir estado parcial (tabela criada sem revisao registada, ou tipo sobrante) que impede idempotencia do setup. O reset forcado remove residuos e garante baseline deterministico antes do `upgrade head`.

### P: Porque o `alembic check` esta nos testes e nao apenas no CI script?

A: Porque faz parte explicita dos criterios da US-011. O teste fixa esta regra no contrato da story e falha quando metadata e schema divergem.

---

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[US-010-VECTOR-STORE-MODEL-EXPLAINED]]
- [[US-009-SUPPORTING-DB-MODELS-EXPLAINED]]
- [[Epics/Database/README|Database Hub]]
