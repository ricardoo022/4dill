# tests/e2e/database/

Testes E2E de `database/` — migrations e modelos contra PostgreSQL real em ambiente completo.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_migrations_e2e.py` | Valida `upgrade head` e `downgrade base` num PostgreSQL real com extensão pgvector |
| `test_models_e2e.py` | Valida CRUD completo de todos os 9 modelos num ciclo de scan real |

## O que é testado

- Migration `001_initial_schema` aplica-se limpa e reverte completamente
- Índice ivfflat cosine criado correctamente no `VectorStore`
- Triggers de `updated_at` activam em updates
- Ciclo completo: Flow → Task → Subtask → Container → Toolcall → cascade delete

## Dependências

- `@pytest.mark.e2e`
- PostgreSQL com extensão pgvector (devcontainer ou CI com serviço)
- `DATABASE_URL` env var

## Módulo de produção

`src/pentest/database/` + `alembic/` — ver `docs/Epics/Database/US-011-ALEMBIC-MIGRATIONS-EXPLAINED.md`
