# tests/unit/

Testes unitários sem dependências externas. Correm em todos os ambientes, incluindo CI a cada PR.

## Subdirectórios

| Directório | Módulo testado |
|---|---|
| `agents/` | `agents/base.py` — base graph, BarrierAwareToolNode |
| `database/` | `database/` — enums, models, migration config |
| `docker/` | `docker/` — DockerClient, DockerConfig, utils |
| `graphiti/` | `graphiti/` — GraphitiClient, GraphitiConfig |
| `models/` | `models/` — Pydantic schemas de pesquisa |
| `recon/` | `recon/` — detectores de backend, orquestrador |
| `skills/` | `skills/loader.py` — FASE index loader |
| `templates/` | `templates/renderer.py` — Jinja2 renderer |
| `tools/` | `tools/` — barriers, browser, search tools, terminal |

## Como correr

```bash
pytest tests/unit/ -v
pytest tests/unit/tools/ -v          # só tools
pytest tests/unit/tools/test_barriers.py::TestSubtaskList -v  # teste específico
```

## Ficheiros raiz

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_devcontainer_config.py` | Valida configuração do devcontainer (portos, serviços, env vars) |
| `test_project_structure.py` | Valida estrutura de ficheiros e módulos do projecto |
