---
tags: [database]
---

# US-006: SQLAlchemy Async Connection Pool — Explicação Detalhada

Este documento explica a implementação do módulo de base de dados (`src/pentest/database/`), incluindo gerenciamento assíncrono de conexões, pool robusto, tratamento de erros customizado, e logging estruturado com structlog.

---

## Contexto

O LusitAI AI Pentest é uma aplicação **async-first** em Python 3.12+. Todas as operações I/O (rede, disco, banco de dados) devem ser **não-bloqueantes** para permitir paralelismo eficiente no agente. O módulo de database fornece:

1. **Engine assíncrono** do SQLAlchemy 2.0 com asyncpg (driver PostgreSQL nativo async)
2. **Pool robusto** com parametrização estrita para evitar vazamento de conexões
3. **Session factory** que gerencia o ciclo de vida (acquire → execute → commit/rollback → release)
4. **Logging estruturado** com structlog para rastreabilidade em produção
5. **Exceções customizadas** que preservam contexto (hostname, porta)

---

## Arquitetura de Alto Nível

```
┌─────────────────────────────────────────────────────────┐
│ Aplicação (Agents, Controllers)                         │
├─────────────────────────────────────────────────────────┤
│  async def scan():                                      │
│      async with get_session() as session:               │
│          await session.execute(...)  # Query            │
│          # Auto-commit on success                       │
└─────────────────────────────────────────────────────────┘
              ↓ (context manager)
┌─────────────────────────────────────────────────────────┐
│ get_session()  [@asynccontextmanager]                   │
│  - Cria AsyncSession via _async_session_factory         │
│  - yield session                                        │
│  - Commit automático (sucesso) / Rollback (exceção)     │
│  - session.close() no finally                           │
└─────────────────────────────────────────────────────────┘
              ↓ (usa engine interno)
┌─────────────────────────────────────────────────────────┐
│ AsyncEngine (create_async_engine)                       │
│  - Pool: pool_size=10, max_overflow=20                  │
│  - pool_timeout=30s, pool_recycle=1800s                 │
│  - Driver: asyncpg (não-bloqueante)                     │
└─────────────────────────────────────────────────────────┘
              ↓ (TCP)
┌─────────────────────────────────────────────────────────┐
│ PostgreSQL (db:5432 no devcontainer)                    │
└─────────────────────────────────────────────────────────┘
```

---

## Módulo 1: Exceções Customizadas (`exceptions.py`)

### Ficheiro Completo

```python
"""Database-related exceptions for the PentestAI application."""


class DatabaseConnectionError(Exception):
    """Raised when a database connection cannot be established or verified.

    Attributes:
        message: Human-readable error message with connection details.
        hostname: The hostname that failed to connect.
        port: The port that failed to connect.
    """

    def __init__(
        self,
        message: str,
        hostname: str | None = None,
        port: int | None = None,
    ) -> None:
        self.hostname = hostname
        self.port = port
        formatted_msg = message
        if hostname or port:
            formatted_msg += f" (hostname={hostname}, port={port})"
        super().__init__(formatted_msg)
```

### Explicação

- Herda de `Exception` — pode ser lançada e apanhada como qualquer exceção Python.
- Armazena `hostname` e `port` como atributos para acesso programático.
- Formata a mensagem com contexto de rede: `"Failed to connect (hostname=db, port=5432)"`.
- **Simples por design** — não faz logging no `__init__`. O logging acontece no `connection.py` onde há mais contexto disponível.

---

## Módulo 2: Gerenciamento de Conexões (`connection.py`)

Este é o módulo principal. Fornece quatro funções:
1. `init_db(url, echo)` — inicializa o engine e session factory (async)
2. `get_session()` — async context manager para adquirir uma sessão
3. `close_db()` — fecha o engine e limpa recursos
4. `_sanitize_url(url)` — remove password antes de logging

### Estado Global do Módulo

```python
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker | None = None
```

Ambos começam como `None` e são inicializados por `init_db()`. Este padrão "module-level singleton" permite que qualquer parte da aplicação importe `get_session()` sem passar o engine explicitamente.

### `_sanitize_url()`

```python
def _sanitize_url(database_url: str) -> str:
    try:
        parsed = urlparse(database_url)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            netloc = f"{parsed.username}:***@{netloc}" if parsed.username else f"***@{netloc}"
            return f"{parsed.scheme}://{netloc}{parsed.path}"
    except Exception:
        pass
    return database_url
```

**Por que existe:** Previne que passwords apareçam em logs. Usa `urlparse` para extrair componentes e reconstrói a URL com `***` no lugar da password. Se o parsing falhar, retorna a URL original (fail-open para não bloquear logging).

### `init_db()`

```python
async def init_db(database_url: str, echo: bool = False) -> None:
```

**Passo 1 — Validação da URL:**
```python
if not database_url.startswith("postgresql+asyncpg://"):
    raise ValueError(...)
```
Rejeita qualquer URL que não use o driver `asyncpg`. Isto previne erros confusos se alguém passar uma URL de MySQL ou SQLite.

**Passo 2 — Criação do Engine:**
```python
_engine = create_async_engine(
    database_url,
    echo=echo,
    pool_size=10,       # Conexões permanentes no pool
    max_overflow=20,    # Conexões temporárias quando pool esgotado
    pool_timeout=30,    # Timeout para obter conexão (segundos)
    pool_recycle=1800,  # Reciclar conexões a cada 30 minutos
)
```

Parâmetros do pool (matching PentAGI Go config):

| Parâmetro | Valor | Significado |
|---|---|---|
| `pool_size` | 10 | Conexões always-alive no pool |
| `max_overflow` | 20 | Conexões extras temporárias (total max: 30) |
| `pool_timeout` | 30s | Tempo máximo de espera por uma conexão |
| `pool_recycle` | 1800s | Reconectar após 30 min (previne stale connections) |

**Passo 3 — Verificação de Conexão:**
```python
await _verify_connection()
```
Chama `_verify_connection()` que executa `SELECT 1` para confirmar que o PostgreSQL está acessível. **Fail-fast** — se a BD não estiver disponível, falha imediatamente em vez de esperar pela primeira query real.

**Passo 4 — Session Factory:**
```python
_async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

`expire_on_commit=False` — após commit, os objetos ORM mantêm os seus atributos em memória (não forçam lazy-load na próxima leitura). Essencial para async porque lazy-loading requer I/O síncrono.

**Error handling:** Exceções de conexão são re-raised como `DatabaseConnectionError` com hostname/port extraídos da URL.

### `_verify_connection()`

```python
async def _verify_connection() -> None:
    if _engine is None:
        raise DatabaseConnectionError("Database engine not initialized", ...)
    async with _engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
```

Abre uma conexão raw (não uma session) e executa `SELECT 1`. Se falhar, extrai hostname/port do engine URL e lança `DatabaseConnectionError` com `from exc` para preservar a chain de exceções.

### `get_session()`

```python
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() before using get_session().")

    session: AsyncSession = _async_session_factory()
    try:
        yield session
        await session.commit()      # Sucesso → commit
    except Exception as exc:
        await session.rollback()    # Erro → rollback
        raise
    finally:
        await session.close()       # Sempre fecha
```

**Ciclo de vida:**
1. `__aenter__`: Cria `AsyncSession`, inicia transação implícita
2. `yield`: Entrega sessão ao caller
3. Se **sucesso**: `commit()` — persiste todas as mudanças
4. Se **exceção**: `rollback()` — reverte tudo, re-raises a exceção
5. `finally`: `close()` — **sempre** fecha a sessão e devolve a conexão ao pool

**Uso típico:**
```python
async with get_session() as session:
    result = await session.execute(text("SELECT * FROM flows"))
    flows = result.fetchall()
    # Auto-commit ao sair do bloco com sucesso
```

### `close_db()`

```python
async def close_db() -> None:
    global _engine, _async_session_factory
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None
    _async_session_factory = None
```

Dispõe do pool de conexões (fecha todas as conexões abertas) e reseta o estado global. Deve ser chamada no shutdown da aplicação. Se chamada sem engine inicializado, é um no-op com warning log.

---

## API Pública (`__init__.py`)

```python
from pentest.database.connection import close_db, get_session, init_db
from pentest.database.exceptions import DatabaseConnectionError

__all__ = ["DatabaseConnectionError", "close_db", "get_session", "init_db"]
```

Os consumidores importam diretamente de `pentest.database`:
```python
from pentest.database import init_db, get_session, close_db, DatabaseConnectionError
```

---

## Uso no Ciclo de Scan

```python
# Startup (em controller/flow.py)
await init_db(os.getenv("DATABASE_URL"))

# Durante o scan
async with get_session() as session:
    flow = Flow(target="example.com", status=FlowStatus.RUNNING)
    session.add(flow)
    # Auto-commit

# Shutdown
await close_db()
```

---

## Parâmetros do Pool — Guia de Tuning

| Cenário | pool_size | max_overflow | Notas |
|---|---|---|---|
| Dev/local | 5 | 5 | Menos conexões, suficiente para desenvolvimento |
| Produção (atual) | 10 | 20 | Default do projeto, matches PentAGI |
| Alto throughput | 20 | 30 | Para scans paralelos intensivos |

**Regra geral:** `pool_size` = número esperado de conexões simultâneas no steady-state. `max_overflow` = margem para picos. Total nunca excede `pool_size + max_overflow`.

---

## Testes de Integração

Os testes vivem em `tests/integration/database/test_connection.py` e usam `@pytest.mark.integration`.

**Fixture de disponibilidade:** Um fixture `db_available` verifica se o PostgreSQL está acessível e faz `pytest.skip` se não estiver. Testes que precisam de BD real usam este fixture (ou `db_session` que o inclui).

**Cobertura dos testes:**

| Teste | O que valida |
|---|---|
| `test_init_db_success` | Engine e session factory criados com URL válida |
| `test_init_db_invalid_url` | `ValueError` para URL não-asyncpg |
| `test_init_db_unreachable` | `DatabaseConnectionError` para host inacessível |
| `test_get_session_select_1` | Session funcional com `SELECT 1` |
| `test_session_commit_on_success` | INSERT persiste após saída normal do context |
| `test_session_rollback_on_exception` | INSERT revertido quando exceção é lançada |
| `test_close_db` | Dispose do engine + globals resetados |
| `test_get_session_without_init` | `RuntimeError` sem `init_db()` prévio |
| `test_session_closes_in_finally` | Session sempre fechada via finally |
| `test_database_connection_error_formatting` | Formatação hostname:port na exceção |
| `test_init_db_with_echo_enabled` | Flag echo propagada ao engine |
| `test_multiple_sessions_independent` | Sessões sequenciais retornam resultados independentes |
| `test_concurrent_sessions_respects_pool_limits` | 15 sessões concorrentes via `asyncio.gather` (AC do US-006) |

---

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[PROJECT-STRUCTURE]]
- [[US-007-DATABASE-ENUM-TYPES]]
- [[US-008-CORE-DB-MODELS]]
