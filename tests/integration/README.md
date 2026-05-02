# tests/integration/

Testes de integração que correm contra serviços reais. Requerem PostgreSQL (testcontainers) e/ou Docker daemon. Correm em CI a cada PR.

## Subdirectórios

| Directório | Serviços necessários | O que testa |
|---|---|---|
| `database/` | PostgreSQL (testcontainers) | Connection pool, migrations Alembic, modelos ORM |
| `docker/` | Docker daemon | DockerClient contra daemon real |
| `tools/` | Rede (HTTP) | DuckDuckGo search real |

## Como correr

```bash
pytest tests/integration/ -v -m integration

# Serviço específico
pytest tests/integration/database/ -v -m integration
pytest tests/integration/docker/ -v -m integration

# Com DATABASE_URL explícito (fora do devcontainer)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/testdb \
  pytest tests/integration/database/ -v -m integration
```

## Convenções

- Todos os testes têm `@pytest.mark.integration`
- `asyncio_mode = "auto"` no pytest config — sem `@pytest.mark.asyncio`
- PostgreSQL iniciado via testcontainers (sem setup manual)
- Fora do devcontainer: definir `DATABASE_URL` explicitamente (default usa `pentagidb_test`)

## Ficheiros raiz

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_placeholder.py` | Placeholder para smoke test da camada de integração |
