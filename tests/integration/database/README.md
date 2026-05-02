# tests/integration/database/

Testes de integração de `database/` contra PostgreSQL real (testcontainers).

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_connection.py` | Testa async connection pool: init, acquire/release, `DatabaseConnectionError` |
| `test_migrations.py` | Testa migrations Alembic: `upgrade head`, `downgrade base`, idempotência, schema resultante |
| `test_models.py` | Testa CRUD real: create/read/update flows, tasks, subtasks, cascade delete |

## O que é testado

- Engine async conecta e disponibiliza sessões
- `upgrade head` cria todos os 9 modelos, 10 enums, 6 triggers e índice ivfflat
- `downgrade base` remove tudo limpo
- Cascade delete: eliminar `Flow` remove `Task`, `Subtask`, etc.
- Soft-delete: `deleted_at` preenchido não elimina a linha
- `create_vector_extension()` é idempotente

## Dependências

- `@pytest.mark.integration`
- PostgreSQL via testcontainers (pgvector/pg16)
- `DATABASE_URL` env var (ou default `pentagidb_test`)

## Módulo de produção

`src/pentest/database/` — ver `docs/Epics/Database/`
