---
tags: [docker]
---

# US-013: Docker Client Initialization — Explicacao Detalhada

Este documento explica linha a linha os ficheiros `src/pentest/docker/client.py`, `src/pentest/docker/config.py` e `src/pentest/docker/exceptions.py`, que implementam a inicializacao do cliente Docker no SecureDev PentestAI. E o segundo story do Epic 3 (Docker Sandbox) e a fundacao sobre a qual todos os stories de gestao de containers assentam.

---

## Contexto

O `DockerClient` e a classe central do modulo Docker. A sua responsabilidade na inicializacao e:

1. **Conectar ao daemon Docker** via `docker-py`, com negociacao automatica de versao de API
2. **Ler configuracao** de um modelo Pydantic (`DockerConfig`)
3. **Criar o `data_dir`** no disco para persistencia de dados entre runs
4. **Resolver o `host_dir`** — o caminho no host para volume mounts quando corremos dentro de Docker (DinD)
5. **Garantir que a rede Docker existe** — cria uma rede bridge se nao existir
6. **Registar informacao do daemon** (nome, arquitectura, versao)
7. **Levantar `DockerConnectionError`** se o daemon nao estiver acessivel

Em Go, toda esta logica vive em `pkg/docker/client.go` nas funcoes `NewDockerClient` (linhas 79-152), `getHostDockerSocket` (linhas 610-648), `getHostDataDir` (linhas 653-716) e `ensureDockerNetwork` (linhas 721-738).

---

## Referencia PentAGI (Go)

### `NewDockerClient` (`client.go` linhas 79-152)

```go
func NewDockerClient(db database.Database, cfg *config.Config) (*dockerClient, error) {
    cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
    if err != nil {
        return nil, fmt.Errorf("failed to create docker client: %w", err)
    }

    dataDir, err := filepath.Abs(cfg.DataDir)
    // ... resolve dataDir, create directory, resolve hostDir ...

    if err := ensureDockerNetwork(ctx, cli, cfg.DockerNetwork); err != nil {
        return nil, err
    }

    info, _ := cli.Info(ctx)
    log.Info().Str("name", info.Name).Str("arch", info.Architecture).Msg("docker client initialized")

    return &dockerClient{
        cli:       cli,
        db:        db,
        dataDir:   dataDir,
        hostDir:   hostDir,
        // ...
    }, nil
}
```

A diferenca principal: em Go retorna-se `(*dockerClient, error)`. Em Python, levantamos `DockerConnectionError` diretamente no `__init__`, seguindo o padrao Python de falha no construtor.

---

## `DockerConfig` (`config.py`)

```python
class DockerConfig(BaseModel):
    docker_inside: bool = False
    docker_socket: str = "/var/run/docker.sock"
    docker_network: str = ""
    docker_public_ip: str = "0.0.0.0"
    docker_default_image: str = "debian:latest"
    docker_pentest_image: str = "kalilinux/kali-rolling"
    data_dir: str = "./data"
    docker_work_dir: str = ""

    @field_validator("data_dir")
    @classmethod
    def data_dir_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("data_dir cannot be empty")
        return v
```

| Campo | Tipo | Default | Significado |
|---|---|---|---|
| `docker_inside` | `bool` | `False` | `True` quando corremos dentro de um container Docker (DinD) |
| `docker_socket` | `str` | `"/var/run/docker.sock"` | Caminho do socket Unix para o daemon |
| `docker_network` | `str` | `""` | Nome da rede Docker a usar; `""` = sem rede dedicada |
| `docker_public_ip` | `str` | `"0.0.0.0"` | IP publico do host, para bind de portas |
| `docker_default_image` | `str` | `"debian:latest"` | Imagem de fallback quando o pull da imagem Kali falha |
| `docker_pentest_image` | `str` | `"kalilinux/kali-rolling"` | Imagem primaria para containers de pentest |
| `data_dir` | `str` | `"./data"` | Diretorio de dados no host; **nao pode ser vazio** |
| `docker_work_dir` | `str` | `""` | Override explicito para `host_dir` em ambientes DinD |

**Validacao de `data_dir`:** o campo `data_dir` e validado por `data_dir_not_empty`. Uma string vazia ou so com espacos levanta `ValueError`, que o Pydantic converte em `ValidationError`. Isto protege contra configuracoes invalidas antes de qualquer chamada ao daemon.

---

## `DockerConnectionError` e `DockerImageError` (`exceptions.py`)

```python
class DockerConnectionError(Exception):
    def __init__(self, message: str, socket: str | None = None) -> None:
        self.socket = socket
        formatted_msg = message
        if socket:
            formatted_msg += f" (socket={socket})"
        super().__init__(formatted_msg)

class DockerImageError(Exception):
    """Raised when both the requested image and fallback image fail to pull."""
```

**`DockerConnectionError`** e levantada no `__init__` do `DockerClient` quando `docker.from_env()` falha. Tem o atributo `socket` para que o codigo de chamada (e os logs) possam indicar qual socket falhou. A mensagem inclui o socket automaticamente: `"Connection refused (socket=/var/run/docker.sock)"`.

**`DockerImageError`** e reservada para US-014a (image management) — levantada quando tanto a imagem principal como a de fallback falham no pull.

---

## Funcoes Auxiliares (`client.py`)

### `_get_host_docker_socket()` (linhas 31-75)

```python
def _get_host_docker_socket(client: Any) -> str:
    daemon_host = str(client.api.base_url)
    # Strip unix:// scheme
    if daemon_host.startswith("http+unix://"):
        daemon_host = daemon_host[len("http+unix://"):]
    # ...

    # Verify it is a socket file
    try:
        st = os.stat(daemon_host)
        if not stat_module.S_ISSOCK(st.st_mode):
            return DEFAULT_DOCKER_SOCKET
    except OSError:
        return DEFAULT_DOCKER_SOCKET

    # When inside a container, find the host-side path via mount inspection
    try:
        hostname = socket.gethostname()
        containers = client.containers.list(filters={"status": "running"})
        for container in containers:
            data = client.api.inspect_container(container.id)
            if data.get("Config", {}).get("Hostname") != hostname:
                continue
            for mount in data.get("Mounts", []):
                if mount.get("Destination") == daemon_host:
                    return str(mount["Source"])
    except Exception:
        pass

    return daemon_host
```

**O que faz:** Resolve o caminho real do socket Docker no host quando corremos dentro de um container.

**Fluxo de decisao:**

```
base_url do daemon
       |
       v
E um ficheiro socket?
  Nao --> retorna DEFAULT_DOCKER_SOCKET ("/var/run/docker.sock")
  Sim -->
       |
       v
Inspecionar containers a correr com o mesmo hostname
       |
       +-- Encontrou mount com Destination == daemon_host?
           Sim --> retorna Source (caminho no host)
           Nao --> retorna daemon_host (o proprio caminho)
```

**Equivalente Go:** `getHostDockerSocket` em `client.go` linhas 610-648.

---

### `_get_host_data_dir()` (linhas 78-130)

```python
def _get_host_data_dir(client: Any, data_dir: str, work_dir: str) -> str:
    if work_dir:
        return work_dir  # override explicito

    # Inspecionar containers para encontrar mount que cobre data_dir
    hostname = socket.gethostname()
    containers = client.containers.list(filters={"status": "running"})

    mounts = []
    for container in containers:
        data = client.api.inspect_container(container.id)
        if data.get("Config", {}).get("Hostname") != hostname:
            continue
        for mount in data.get("Mounts", []):
            dest = mount.get("Destination", "")
            if data_dir.startswith(dest):
                mounts.append(mount)

    if not mounts:
        return ""

    # Mount mais especifico (Destination mais longo)
    mounts.sort(key=lambda m: len(m.get("Destination", "")), reverse=True)
    best = mounts[0]

    if best.get("Type") == "bind":
        dest = best["Destination"]
        source = best["Source"]
        delta = data_dir[len(dest):]
        return str(Path(source) / delta.lstrip("/"))

    return ""  # Volume mount nao e utilizavel
```

**O que faz:** Resolve o caminho do `data_dir` no host para que volume mounts nos containers filhos apontem para o local correto.

**Porque e necessario:** Quando o PentestAI corre dentro de um container (`docker_inside=True`), o caminho `/app/data` que vemos dentro nao e o mesmo que o Docker host ve. Para montar `/app/data` num container filho, precisamos do caminho real no host (ex: `/home/user/project/data`). Inspecionamos os mounts do nosso proprio container para encontrar essa correspondencia.

**Fluxo de decisao:**

```
work_dir configurado?
  Sim --> retorna work_dir diretamente (override explícito)
  Nao -->
       |
       v
Inspecionar mounts do container atual
       |
       +-- Nenhum mount cobre data_dir? --> retorna ""
       |
       +-- Mount do tipo "bind" encontrado? --> calcula caminho no host
       |
       +-- Mount do tipo "volume"? --> retorna "" (nao utilizavel)
```

**Equivalente Go:** `getHostDataDir` em `client.go` linhas 653-716.

---

### `_ensure_docker_network()` (linhas 133-156)

```python
def _ensure_docker_network(client: Any, name: str) -> None:
    if not name or name == "host":
        return  # nao fazer nada para "" ou "host"

    try:
        client.networks.get(name)
        return  # ja existe
    except docker.errors.NotFound:
        pass

    client.networks.create(name, driver="bridge")
```

**O que faz:** Garante que a rede Docker com o nome configurado existe. Se nao existir, cria-a como rede bridge.

**Casos especiais:**
- `""` (string vazia) — sem rede dedicada, sai imediatamente
- `"host"` — rede built-in do Docker, nao pode ser criada nem deve ser tocada
- Qualquer outro nome — verifica se existe; cria bridge se necessario (idempotente)

**Equivalente Go:** `ensureDockerNetwork` em `client.go` linhas 721-738.

---

## `DockerClient.__init__()` (linhas 159-229)

```python
class DockerClient:
    def __init__(self, db_session: AsyncSession, config: DockerConfig) -> None:
        # 1. Conectar ao daemon e negociar versao de API
        try:
            self._client = docker.from_env()
            self._client.api.version()  # dispara a negociacao
        except docker.errors.DockerException as exc:
            raise DockerConnectionError(str(exc), socket=config.docker_socket) from exc

        # 2. Guardar campos de configuracao
        self._db = db_session
        self._inside = config.docker_inside
        self._network = config.docker_network
        self._public_ip = config.docker_public_ip
        self._def_image = config.docker_default_image.lower() or _DEFAULT_IMAGE

        # Resolver socket
        self._socket = (
            config.docker_socket if config.docker_socket
            else _get_host_docker_socket(self._client)
        )

        # 3. Resolver e criar data_dir
        self._data_dir = str(Path(config.data_dir).resolve())
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)

        # 4. Resolver host_dir para DinD
        self._host_dir = _get_host_data_dir(
            self._client, self._data_dir, config.docker_work_dir
        )

        # 5. Garantir que a rede existe
        _ensure_docker_network(self._client, self._network)

        # 6. Registar informacao do daemon
        try:
            info = self._client.info()
            logger.debug("docker_client_initialized", extra={
                "docker_name": info.get("Name"),
                "docker_arch": info.get("Architecture"),
                "docker_version": info.get("ServerVersion"),
                "data_dir": self._data_dir,
                "host_dir": self._host_dir,
            })
        except Exception:
            pass  # falha de logging nao deve abortar a inicializacao
```

**Ordem de operacoes e porque importa:**

| Passo | Operacao | Porque esta ordem |
|---|---|---|
| 1 | `docker.from_env()` + `api.version()` | Se o daemon nao estiver acessivel, falhamos cedo antes de qualquer I/O |
| 2 | Guardar config | Estado interno necessario para os passos seguintes |
| 3 | Criar `data_dir` | O directorio tem de existir antes de qualquer mount |
| 4 | Resolver `host_dir` | Requer o cliente Docker ja inicializado (para inspecionar containers) |
| 5 | Criar rede | Idempotente; pode falhar com `APIError` se sem permissoes |
| 6 | Log daemon info | Ultimo — informacao apenas, falha silenciosa intencional |

**`docker.from_env()` vs `client.NewClientWithOpts(client.FromEnv)`:** Sao equivalentes. Ambos lem `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH` e `DOCKER_API_VERSION` do ambiente. A negociacao de versao e feita automaticamente pelo `docker-py` quando chamamos qualquer metodo de API (`api.version()` e apenas para disparar explicitamente).

---

## `get_default_image()` (linhas 224-229)

```python
def get_default_image(self) -> str:
    return self._def_image
```

Retorna a imagem de fallback configurada (`docker_default_image`). Usada por US-014a quando o pull da imagem de pentest falha.

**Nota de normalizacao:** O valor e guardado em lowercase (`config.docker_default_image.lower()`) para garantir consistencia nas comparacoes. Se o campo estiver vazio, usa-se `_DEFAULT_IMAGE = "debian:latest"`.

---

## Exports (`__init__.py`)

```python
from pentest.docker.client import DockerClient
from pentest.docker.config import DockerConfig
from pentest.docker.exceptions import DockerConnectionError, DockerImageError
from pentest.docker.utils import (
    BASE_CONTAINER_PORTS, CONTAINER_PORTS_COUNT,
    MAX_PORT_RANGE, WORK_FOLDER_PATH,
    get_primary_container_ports, primary_terminal_name,
)

__all__ = [
    "DockerClient", "DockerConfig",
    "DockerConnectionError", "DockerImageError",
    "BASE_CONTAINER_PORTS", "CONTAINER_PORTS_COUNT",
    "MAX_PORT_RANGE", "WORK_FOLDER_PATH",
    "get_primary_container_ports", "primary_terminal_name",
]
```

O `__init__.py` consolida a API publica do modulo `docker`. Os consumidores importam tudo de `pentest.docker` sem precisar de conhecer a estrutura interna dos ficheiros.

---

## Testes

### Unit tests (`tests/unit/docker/test_client.py`) — 2 testes

Apenas os casos que genuinamente nao podem usar um daemon real:

| Teste | O que valida |
|---|---|
| `test_init_raises_docker_connection_error` | `docker.from_env()` levanta `DockerException` → wrapped em `DockerConnectionError` com `socket` correcto |
| `test_config_empty_data_dir_raises_validation_error` | `DockerConfig(data_dir="")` levanta `ValidationError` — validacao Pydantic pura |

### Integration tests (`tests/integration/docker/test_client.py`) — 6 testes

Todos usam o daemon Docker real do devcontainer:

| Teste | O que valida | Como valida |
|---|---|---|
| `test_docker_client_connects` | Ligacao ao daemon bem-sucedida | `get_default_image()` retorna `"debian:latest"` |
| `test_get_default_image_returns_configured_value` | Imagem configurada e respeitada | `DockerConfig(docker_default_image="alpine:latest")` |
| `test_data_dir_created_on_disk` | `data_dir` criado no disco | `Path.exists()` + `Path.is_dir()` em path aninhado |
| `test_network_created_if_missing` | Rede bridge criada no Docker | `docker_api.networks.get(net_name).attrs["Driver"] == "bridge"` |
| `test_network_not_recreated_if_exists` | Idempotencia da rede | ID da rede identico em dois inits consecutivos |
| `test_network_skipped_for_host_mode` | Modo `"host"` nao cria redes | Diff do `docker network ls` filtrado por prefixo `test-pentest-` |

**Fixtures chave:**

```python
@pytest.fixture
def docker_api() -> docker.DockerClient:
    """Cliente docker-py directo para assercoes pos-condicao."""
    return docker.from_env()

@pytest.fixture
def net_name() -> str:
    """Nome de rede unico por teste para evitar poluicao entre testes."""
    return f"test-pentest-{uuid.uuid4().hex[:8]}"
```

**Cleanup das redes:** Os testes de rede usam `try/finally` com `contextlib.suppress(docker.errors.NotFound)` para garantir que a rede e sempre removida apos o teste, mesmo que a assercao falhe.

---

## Diagrama de Dependencias

```
US-019 (utils.py — constantes e nomeacao)
  |
  v
US-013 (DockerClient — inicializacao e ligacao)   <-- este story
  |
  +-- US-014a (ensure_image — pull e fallback)
  |     |
  |     v
  +-- US-014b (run_container — criacao do container Kali)
        |
        +-- US-015 (exec_command — execucao de comandos)
        +-- US-016 (file operations — leitura/escrita de ficheiros)
        +-- US-017 (stop/remove — ciclo de vida do container)
              |
              v
           US-018 (cleanup — remocao de containers orfaos)
```

O `DockerClient` e o ponto de entrada de todos os stories subsequentes. US-014a e US-014b estendem esta classe com metodos adicionais.

---

## Related Notes

- [Docs Home](../../README.md)
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[DOCKER-DAEMON-TROUBLESHOOTING]]
- [[US-014A-IMAGE-MANAGEMENT-EXPLAINED]]
- [[US-019-CONTAINER-UTILITIES-EXPLAINED]]
