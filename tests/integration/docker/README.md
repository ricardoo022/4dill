# tests/integration/docker/

Testes de integração de `docker/` contra Docker daemon real.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_client.py` | Testa `DockerClient` contra daemon real: conexão, versão API, `ensure_image()` |

## O que é testado

- `DockerClient` conecta ao daemon local
- Versão de API negociada corretamente
- `ensure_image()` faz pull de uma imagem leve e cache na segunda chamada
- `DockerConnectionError` lançado quando daemon não está disponível

## Dependências

- `@pytest.mark.integration`
- Docker daemon a correr no host ou DinD (devcontainer)

## Módulo de produção

`src/pentest/docker/` — ver `docs/Epics/Docker Sandbox/US-013-DOCKER-CLIENT-EXPLAINED.md`
