# tests/unit/docker/

Testes unitários de `docker/` — DockerClient, DockerConfig e funções utilitárias de containers.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_client.py` | Testa `DockerClient`: init, `ensure_image()` (cache hit, pull, fallback), `DockerImageError` |
| `test_utils.py` | Testa `primary_terminal_name()`, `get_primary_container_ports()`, alocação determinística de portos |

## O que é testado

- `DockerConfig.pull_timeout` default 300s
- `ensure_image()`: cache hit não chama pull; fallback activado quando imagem principal falha
- `DockerImageError` lançado quando imagem e fallback falham
- `primary_terminal_name(flow_id)` gera nome consistente
- `get_primary_container_ports(flow_id)` aloca portos de forma determinística sem colisão

## Módulo de produção

`src/pentest/docker/` — ver `docs/Epics/Docker Sandbox/`
