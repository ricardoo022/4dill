# tests/unit/database/

Testes unitários de `database/` — validação de enums, models SQLAlchemy e configuração de migrations.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_enums.py` | Valida os 10 StrEnum types: nomes, valores lowercase, SQLAlchemy wrappers |
| `test_models.py` | Valida modelos ORM: tablenames, colunas, defaults, cascade, soft-delete, índice ivfflat |
| `test_migration_config_us011.py` | Valida configuração Alembic: `alembic.ini`, `env.py` async, leitura de `DATABASE_URL` |

## O que é testado

- Todos os enums têm `values_callable` para serialização lowercase
- `Flow`, `Task`, `Subtask`, `Container`, `Toolcall`, `Msgchain`, `Termlog`, `Msglog`, `VectorStore` têm os atributos corretos
- Soft-delete: `deleted_at` presente em `Flow`
- `VectorStore.embedding` usa `Vector(1536)` com índice ivfflat cosine
- `alembic.ini` lê `DATABASE_URL` do ambiente e não tem URL hardcoded

## Módulo de produção

`src/pentest/database/` — ver `docs/Epics/Database/`
