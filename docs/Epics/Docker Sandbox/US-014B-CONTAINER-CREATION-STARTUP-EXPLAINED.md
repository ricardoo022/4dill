---
tags: [docker]
---

# US-014b: Container Creation and Startup — Explicacao Detalhada

Este documento explica as alteracoes feitas em `src/pentest/docker/client.py`, `tests/integration/docker/test_client.py`, `tests/unit/docker/test_client.py` e `tests/integration/conftest.py` para implementar a criacao/arranque de containers da US-014b com persistencia de estado e testes de prova.

---

## Contexto

A US-014b fecha o gap entre "ter cliente Docker inicializado" (US-013) e "ter imagem resolvida" (US-014a), adicionando a operacao principal do runtime: criar um container isolado por flow e colocá-lo em estado `running`.

Responsabilidades principais desta entrega:

1. Construir configuracao de sandbox segura (hostname, `/work`, restart policy, logs, entrypoint keep-alive).
2. Reutilizar dependencias anteriores (`ensure_image`, `primary_terminal_name`, `get_primary_container_ports`).
3. Persistir lifecycle do container na DB (`starting` -> `running`, `failed` em erro terminal).
4. Implementar ramificacao de rede correta (bridge vs host).
5. Cobrir comportamento com testes unitarios e de integracao.

---

## Referencia PentAGI (Go)

A historia referencia `RunContainer` (`client.go` linhas 220-366). Nesta branch, o submodule Go nao estava disponivel para citar o snippet literal no workspace, mas o mapeamento funcional foi mantido conforme os Technical Notes da US:

- `client.containers.run(..., detach=True)`
- volume bind para `/work`
- network `bridge` com port bindings ou `host` sem bindings
- hostname CRC32 do nome do container

---

## `DockerClient` — run container e helpers (`src/pentest/docker/client.py`)

### Bloco adicionado: imports e dependencias de persistencia

```python
import binascii
from docker.types import LogConfig

from pentest.database.enums import ContainerStatus, ContainerType
from pentest.database.queries.containers import (
    CreateContainerParams,
    create_container,
    update_container_image,
    update_container_status,
    update_container_status_local_id,
)
from pentest.docker.utils import (
    CONTAINER_LOCAL_CWD_TEMPLATE,
    DEFAULT_DOCKER_SOCKET,
    WORK_FOLDER_PATH,
    get_primary_container_ports,
    primary_terminal_name,
)
```

| Bloco | Porque existe |
|---|---|
| `binascii` | Implementar hostname CRC32 (8 hex chars) pedido na US |
| `LogConfig` | Configurar `json-file` com `max-size=10m`, `max-file=5` |
| `queries.containers` | Persistir estado do container durante o lifecycle |
| `utils` (US-019) | Reuso de naming deterministico e formula de portas |

### Helpers novos

```python
@staticmethod
def _crc32_hostname(name: str) -> str:
    return format(binascii.crc32(name.encode()) & 0xFFFFFFFF, "08x")

def _resolve_flow_paths(self, flow_id: int) -> tuple[Path, Path]:
    flow_dir_name = CONTAINER_LOCAL_CWD_TEMPLATE.format(flow_id)
    data_flow_dir = Path(self._data_dir) / flow_dir_name
    host_root = Path(self._host_dir) if self._host_dir else Path(self._data_dir)
    host_flow_dir = host_root / flow_dir_name
    return data_flow_dir, host_flow_dir

def _build_port_bindings(self, flow_id: int) -> dict[str, tuple[str, int]]:
    ports = get_primary_container_ports(flow_id)
    return {f"{port}/tcp": (self._public_ip, port) for port in ports}

def _build_volumes(self, host_flow_dir: Path) -> dict[str, dict[str, str]]:
    volumes: dict[str, dict[str, str]] = {
        str(host_flow_dir): {"bind": WORK_FOLDER_PATH, "mode": "rw"}
    }
    if self._inside:
        volumes[self._socket] = {"bind": self._socket, "mode": "rw"}
    return volumes
```

| Helper | Input | Output | Papel na US-014b |
|---|---|---|---|
| `_crc32_hostname` | `name` | hash hex 8 chars | AC de hostname |
| `_resolve_flow_paths` | `flow_id` | (`data_flow_dir`, `host_flow_dir`) | AC de diretoria por flow |
| `_build_port_bindings` | `flow_id` | map `port/tcp -> (public_ip, port)` | AC bridge + formula US-019 |
| `_build_volumes` | `host_flow_dir` | volumes dict | mount `/work` + socket opcional |

### Builder de configuracao de runtime

```python
def _build_run_kwargs(...):
    kwargs: dict[str, Any] = {
        "name": container_name,
        "hostname": self._crc32_hostname(container_name),
        "working_dir": WORK_FOLDER_PATH,
        "entrypoint": ["tail", "-f", "/dev/null"],
        "detach": True,
        "volumes": self._build_volumes(host_flow_dir),
        "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 5},
        "log_config": LogConfig(
            type=LogConfig.types.JSON,
            config={"max-size": "10m", "max-file": "5"},
        ),
    }
    if host_config:
        kwargs.update(host_config)

    if self._network == "host":
        kwargs["network_mode"] = "host"
        kwargs.pop("ports", None)
        kwargs.pop("network", None)
    else:
        kwargs["ports"] = self._build_port_bindings(flow_id)
        if self._network:
            kwargs["network"] = self._network
        kwargs.pop("network_mode", None)

    # Runtime-controlled safety fields are not overrideable from host_config.
    kwargs["name"] = container_name
    kwargs["hostname"] = self._crc32_hostname(container_name)
    kwargs["working_dir"] = WORK_FOLDER_PATH
    kwargs["entrypoint"] = ["tail", "-f", "/dev/null"]
    kwargs["detach"] = True
    kwargs["restart_policy"] = {"Name": "on-failure", "MaximumRetryCount": 5}
    kwargs["log_config"] = LogConfig(
        type=LogConfig.types.JSON,
        config={"max-size": "10m", "max-file": "5"},
    )
    kwargs["volumes"] = self._build_volumes(host_flow_dir)
    return kwargs
```

#### Porque e assim?

Mesmo aceitando `host_config` externo, os campos criticos de isolamento sao reescritos no final para evitar overrides inseguros (ex.: alterar entrypoint, desativar restart policy, trocar mounts).

### Metodo principal: `run_container(...)`

```python
async def run_container(
    self,
    name: str,  # noqa: ARG002 - kept for API compatibility with story signature
    container_type: ContainerType,
    flow_id: int,
    image: str,
    host_config: dict[str, Any] | None,
) -> RuntimeContainer:
    container_name = primary_terminal_name(flow_id)
    resolved_image = self.ensure_image(image)
    data_flow_dir, host_flow_dir = self._resolve_flow_paths(flow_id)
    data_flow_dir.mkdir(parents=True, exist_ok=True)
    host_flow_dir.mkdir(parents=True, exist_ok=True)

    db_container = await create_container(
        self._db,
        CreateContainerParams(
            type=container_type,
            name=container_name,
            image=resolved_image,
            status=ContainerStatus.STARTING,
            local_dir=str(data_flow_dir),
            flow_id=flow_id,
        ),
    )

    run_kwargs = self._build_run_kwargs(...)

    try:
        runtime_container = self._client.containers.run(resolved_image, **run_kwargs)
        final_image = resolved_image
    except docker.errors.DockerException as first_exc:
        if resolved_image == self._def_image:
            await update_container_status(self._db, db_container.id, ContainerStatus.FAILED)
            raise

        final_image = self.ensure_image(self._def_image)
        await update_container_image(self._db, db_container.id, final_image)
        try:
            runtime_container = self._client.containers.run(final_image, **run_kwargs)
        except docker.errors.DockerException:
            await update_container_status(self._db, db_container.id, ContainerStatus.FAILED)
            raise

    return await update_container_status_local_id(
        self._db,
        db_container.id,
        ContainerStatus.RUNNING,
        runtime_container.id,
    )
```

Fluxo de controlo (bridge/host + retry):

```text
run_container(flow_id, image)
  |
  +-- primary_terminal_name(flow_id)
  +-- ensure_image(image)
  +-- create DB row (status=starting)
  +-- build kwargs
       |
       +-- network == host?
       |     +-- yes: network_mode=host, sem ports
       |     +-- no : ports via get_primary_container_ports(flow_id)
  |
  +-- containers.run(resolved_image)
       |
       +-- sucesso -> status=running + local_id
       +-- falha
             |
             +-- resolved_image == default? -> status=failed + raise
             +-- senao:
                   ensure_image(default)
                   update image na DB
                   retry run(default)
                      +-- sucesso -> status=running + local_id
                      +-- falha   -> status=failed + raise
```

---

## Testes unitarios adicionados (`tests/unit/docker/test_client.py`)

### Testes novos para `run_container`

```python
@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.create_container")
async def test_run_container_uses_canonical_name_and_bridge_ports(...):
    ...
    assert called_kwargs["name"] == "pentestai-terminal-1"
    assert called_kwargs["hostname"] == DockerClient._crc32_hostname("pentestai-terminal-1")
    assert called_kwargs["ports"] == {
        "28002/tcp": ("0.0.0.0", 28002),
        "28003/tcp": ("0.0.0.0", 28003),
    }

@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.create_container")
async def test_run_container_host_mode_disables_ports(...):
    ...
    assert called_kwargs["network_mode"] == "host"
    assert "ports" not in called_kwargs

@patch("pentest.docker.client.update_container_status")
@patch("pentest.docker.client.update_container_status_local_id")
@patch("pentest.docker.client.update_container_image")
@patch("pentest.docker.client.create_container")
async def test_run_container_retries_with_default_image_on_creation_failure(...):
    ...
    assert ...call_args_list[0][0][0] == "custom:image"
    assert ...call_args_list[1][0][0] == "debian:latest"
```

| Teste | O que prova |
|---|---|
| `...canonical_name_and_bridge_ports` | naming canonico + CRC32 + portas bridge |
| `...host_mode_disables_ports` | host mode remove port bindings |
| `...retries_with_default_image...` | retry com default image em erro de criacao |

---

## Testes de integracao adicionados (`tests/integration/docker/test_client.py`)

### Cobertura de comportamento real

```python
@pytest.mark.integration
async def test_run_container_bridge_mode_starts_container_with_expected_config(...):
    ...
    assert attrs["Config"]["WorkingDir"] == "/work"
    assert attrs["HostConfig"]["RestartPolicy"]["Name"] == "on-failure"
    assert "28002/tcp" in (attrs["HostConfig"].get("PortBindings") or {})
    runtime.exec_run("sh -lc 'echo ready > /work/test.txt'")
    assert (tmp_path / "flow-1" / "test.txt").exists()
```

```python
@pytest.mark.integration
async def test_run_container_persists_db_status_running_with_local_id(...):
    async with get_session() as session:
        flow = await create_flow(...)
        result = await client.run_container(...)
        rows = await get_flow_containers(session, flow.id)
        assert rows[0].status == ContainerStatus.RUNNING
        assert rows[0].local_id == result.local_id
```

```python
@pytest.mark.integration
async def test_run_container_invalid_image_and_default_failure_marks_failed(...):
    with (
        patch.object(client, "ensure_image", side_effect=["custom/image:missing", existing_local_image]),
        patch("docker.models.containers.ContainerCollection.run", side_effect=docker.errors.APIError(...)),
        pytest.raises(docker.errors.APIError),
    ):
        await client.run_container(...)
    assert rows[0].status == ContainerStatus.FAILED
```

| Grupo | Prova funcional |
|---|---|
| Bridge mode | config do container + mount + portas + ficheiro host round-trip |
| Host mode | `network_mode=host` sem `PortBindings` |
| Persistencia DB | estado `running` e `local_id` real apos arranque |
| Retry/Failure | retry para default e `failed` no erro terminal |

---

## Fixtures de integracao partilhadas (`tests/integration/conftest.py`)

```python
from tests.integration.database.conftest import db_schema, db_session

__all__ = ["db_schema", "db_session"]
```

Este ficheiro expõe fixtures de DB para subpackages de integracao, permitindo aos testes Docker reutilizar sessoes reais quando precisam de validar estado em PostgreSQL.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/docker/client.py` | Implementacao de `run_container` + helpers de runtime/network/volume + persistencia DB |
| `tests/unit/docker/test_client.py` | Testes unitarios de composicao de kwargs, host mode e retry |
| `tests/integration/docker/test_client.py` | Testes de prova real (Docker + DB) para todos os cenarios da US-014b |
| `tests/integration/conftest.py` | Re-export de fixtures de DB para integracao cross-package |

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-013-DOCKER-CLIENT-EXPLAINED]]
- [[US-014A-IMAGE-MANAGEMENT-EXPLAINED]]
- [[US-019-CONTAINER-UTILITIES-EXPLAINED]]
- [[Epics/Docker Sandbox/README|Docker Sandbox Hub]]
