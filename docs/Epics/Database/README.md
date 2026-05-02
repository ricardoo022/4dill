---
tags: [database]
---

# Database

Hub para as notas de PostgreSQL, SQLAlchemy e modelos persistentes.

## Docs

| Doc | Foco |
|---|---|
| [Database Setup Guide](../../DATABASE_SETUP.md) | setup local/manual de PostgreSQL e testes |
| [US-006 SQLAlchemy Pool](US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED.md) | `database/connection.py` |
| [US-007 Database Enum Types](US-007-DATABASE-ENUM-TYPES.md) | `database/enums.py` |
| [US-008 Core DB Models](US-008-CORE-DB-MODELS.md) | `database/models.py` — Flow, Task, Subtask |
| [US-009 Supporting DB Models](US-009-SUPPORTING-DB-MODELS-EXPLAINED.md) | `database/models.py` — Container, Toolcall, Msgchain, Termlog, Msglog |
| [US-010 Vector Store Model](US-010-VECTOR-STORE-MODEL-EXPLAINED.md) | `database/models.py` + pgvector, testes unit/integration/e2e |
| [US-011 Alembic Migrations](US-011-ALEMBIC-MIGRATIONS-EXPLAINED.md) | `alembic.ini`, `alembic/env.py`, migration inicial |

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[USER-STORIES]]
