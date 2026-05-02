---
tags: [docker]
---

# US-019: Container Name and Port Utilities — Explicacao Detalhada

Este documento explica linha a linha o ficheiro `src/pentest/docker/utils.py`, que define as constantes e funcoes utilitarias para nomeacao de containers e alocacao de portas no SecureDev PentestAI. E o primeiro story do Epic 3 (Docker Sandbox) porque todos os outros stories dependem destas constantes e funcoes.

---

## Contexto

O PentAGI usa um padrao deterministico para:

- **Nomes de containers** — cada scan (flow) gera um container com nome previsivel: `pentestai-terminal-{flow_id}`
- **Alocacao de portas** — cada container recebe 2 portas calculadas por formula, sem conflitos entre scans simultaneos

Em Go, estas utilidades vivem em dois ficheiros:
- `pkg/docker/client.go` linhas 29-40 (constantes) e 70-77 (`GetPrimaryContainerPorts`)
- `pkg/tools/terminal.go` linha 419 (`PrimaryTerminalName`)

Em Python, centralizamos tudo em `src/pentest/docker/utils.py` porque:

1. **US-013** (Docker Client) precisa das constantes para configuracao
2. **US-014a/b** (Container Lifecycle) precisa de `primary_terminal_name()` e `get_primary_container_ports()`
3. **US-015** (Exec) precisa do `WORK_FOLDER_PATH`
4. Ter tudo num unico modulo evita imports circulares

---

## Referencia PentAGI (Go)

### Constantes (`client.go` linhas 29-40)

```go
const WorkFolderPathInContainer = "/work"
const BaseContainerPortsNumber = 28000

const (
    defaultImage                = "debian:latest"
    defaultDockerSocketPath     = "/var/run/docker.sock"
    containerPrimaryTypePattern = "-terminal-"
    containerLocalCwdTemplate   = "flow-%d"
    containerPortsNumber        = 2
    limitContainerPortsNumber   = 2000
)
```

### Funcao de Portas (`client.go` linhas 70-77)

```go
func GetPrimaryContainerPorts(flowID int64) []int {
    ports := make([]int, containerPortsNumber)
    for i := 0; i < containerPortsNumber; i++ {
        delta := (int(flowID)*containerPortsNumber + i) % limitContainerPortsNumber
        ports[i] = BaseContainerPortsNumber + delta
    }
    return ports
}
```

---

## Constantes Publicas (linhas 7-19)

```python
WORK_FOLDER_PATH: str = "/work"
BASE_CONTAINER_PORTS: int = 28000
CONTAINER_PORTS_COUNT: int = 2
MAX_PORT_RANGE: int = 2000
```

| Python | Go | Valor | Uso |
|---|---|---|---|
| `WORK_FOLDER_PATH` | `WorkFolderPathInContainer` | `"/work"` | Diretorio de trabalho montado dentro do container Kali |
| `BASE_CONTAINER_PORTS` | `BaseContainerPortsNumber` | `28000` | Porto base para alocacao |
| `CONTAINER_PORTS_COUNT` | `containerPortsNumber` | `2` | Numero de portas por container |
| `MAX_PORT_RANGE` | `limitContainerPortsNumber` | `2000` | Range maximo antes de wrap-around |

**Porque 2 portas?** O PentAGI aloca 2 portas por container para permitir servicos auxiliares (ex: reverse shells, listeners HTTP). A formula garante que nao ha colisoes entre flows simultaneos ate 1000 flows concorrentes (`MAX_PORT_RANGE / CONTAINER_PORTS_COUNT = 1000`).

**Porque wrap-around a 2000?** Portas acima de 30000 (`28000 + 2000`) entrariam na faixa efemera do Linux (32768-60999). O wrap-around mantem as portas no range 28000-29999.

---

## Constantes Internas (linhas 21-26)

```python
DEFAULT_IMAGE: str = "debian:latest"
DEFAULT_DOCKER_SOCKET: str = "/var/run/docker.sock"
CONTAINER_PRIMARY_TYPE_PATTERN: str = "-terminal-"
CONTAINER_LOCAL_CWD_TEMPLATE: str = "flow-{}"
```

Estas constantes nao fazem parte dos acceptance criteria do US-019, mas estao definidas aqui porque:

- **`DEFAULT_IMAGE`** — imagem fallback quando o pull da imagem Kali falha (US-014a)
- **`DEFAULT_DOCKER_SOCKET`** — caminho do socket Docker para bind-mount (US-013)
- **`CONTAINER_PRIMARY_TYPE_PATTERN`** — padrao para filtrar containers do PentestAI (US-018 cleanup)
- **`CONTAINER_LOCAL_CWD_TEMPLATE`** — template para diretorio de trabalho no host: `flow-{flow_id}` (US-014b)

**Nota:** Em Go usa-se `"flow-%d"` (format verb). Em Python usamos `"flow-{}"` para compatibilidade com `str.format()` e f-strings.

---

## `primary_terminal_name()` (linhas 29-35)

```python
def primary_terminal_name(flow_id: int) -> str:
    return f"pentestai-terminal-{flow_id}"
```

**O que faz:** Gera o nome deterministico do container para um dado flow.

**Equivalente Go:** `PrimaryTerminalName(flowID)` em `terminal.go` linha 419.

**Exemplos:**

| `flow_id` | Resultado |
|---|---|
| `0` | `"pentestai-terminal-0"` |
| `1` | `"pentestai-terminal-1"` |
| `999` | `"pentestai-terminal-999"` |

**Porque deterministico?** Outros modulos (ex: `exec_command` no US-015) precisam de encontrar o container pelo nome. Se o nome fosse aleatorio, teriamos de manter um mapeamento flow_id -> container_name em memoria ou na DB. O padrao deterministico elimina essa necessidade.

---

## `get_primary_container_ports()` (linhas 38-52)

```python
def get_primary_container_ports(flow_id: int) -> list[int]:
    return [
        BASE_CONTAINER_PORTS + ((flow_id * CONTAINER_PORTS_COUNT + i) % MAX_PORT_RANGE)
        for i in range(CONTAINER_PORTS_COUNT)
    ]
```

**O que faz:** Calcula as 2 portas alocadas a um container, usando uma formula deterministica que evita colisoes.

**Equivalente Go:** `GetPrimaryContainerPorts(flowID)` em `client.go` linhas 70-77.

### Formula Explicada

Para cada indice `i` (0 e 1):

```
porta = 28000 + ((flow_id * 2 + i) % 2000)
```

Decompondo:
1. `flow_id * 2` — cada flow "ocupa" 2 posicoes no espaco de portas
2. `+ i` — indice dentro do par (0 = primeira porta, 1 = segunda)
3. `% 2000` — wrap-around para manter no range
4. `+ 28000` — offset base

### Tabela de Exemplos

| `flow_id` | Calculo porta 0 | Calculo porta 1 | Resultado |
|---|---|---|---|
| `0` | `28000 + (0*2+0) % 2000 = 28000` | `28000 + (0*2+1) % 2000 = 28001` | `[28000, 28001]` |
| `1` | `28000 + (1*2+0) % 2000 = 28002` | `28000 + (1*2+1) % 2000 = 28003` | `[28002, 28003]` |
| `2` | `28000 + (2*2+0) % 2000 = 28004` | `28000 + (2*2+1) % 2000 = 28005` | `[28004, 28005]` |
| `999` | `28000 + (999*2+0) % 2000 = 29998` | `28000 + (999*2+1) % 2000 = 29999` | `[29998, 29999]` |
| `1000` | `28000 + (1000*2+0) % 2000 = 28000` | `28000 + (1000*2+1) % 2000 = 28001` | `[28000, 28001]` |

**flow_id=1000 e o ponto de wrap-around:** `1000 * 2 = 2000`, e `2000 % 2000 = 0`. A partir daqui os portos repetem. Na pratica, isto significa que o sistema suporta ate **1000 scans simultaneos** sem colisao de portas.

---

## Exports (`__init__.py`)

```python
from pentest.docker.utils import (
    BASE_CONTAINER_PORTS,
    CONTAINER_PORTS_COUNT,
    MAX_PORT_RANGE,
    WORK_FOLDER_PATH,
    get_primary_container_ports,
    primary_terminal_name,
)

__all__ = [
    "BASE_CONTAINER_PORTS",
    "CONTAINER_PORTS_COUNT",
    "MAX_PORT_RANGE",
    "WORK_FOLDER_PATH",
    "get_primary_container_ports",
    "primary_terminal_name",
]
```

O `__init__.py` re-exporta apenas a API publica. As constantes internas (`DEFAULT_IMAGE`, etc.) sao importadas diretamente de `pentest.docker.utils` pelos modulos que precisarem.

**Uso pelos consumidores:**

```python
# Import limpo via package
from pentest.docker import primary_terminal_name, get_primary_container_ports

name = primary_terminal_name(42)          # "pentestai-terminal-42"
ports = get_primary_container_ports(42)   # [28084, 28085]
```

---

## Testes (`tests/unit/docker/test_utils.py`)

14 testes unitarios organizados em 4 classes:

| Classe | Testes | O que valida |
|---|---|---|
| `TestConstants` | 4 | Valores das 4 constantes publicas |
| `TestPrimaryTerminalName` | 3 | Nomeacao com flow_id=0, 1, 999 |
| `TestGetPrimaryContainerPorts` | 6 | Formula com flow_id=0,1,2, wrap-around a 1000, tipo e tamanho do resultado |
| `TestPortUniqueness` | 1 | 100 flow IDs consecutivos produzem pares unicos |

**Cobertura dos acceptance criteria:**

| Criterio | Teste |
|---|---|
| `primary_terminal_name(1)` returns `"pentestai-terminal-1"` | `TestPrimaryTerminalName::test_flow_id_1` |
| `primary_terminal_name(999)` returns `"pentestai-terminal-999"` | `TestPrimaryTerminalName::test_flow_id_999` |
| `get_primary_container_ports(0)` returns `[28000, 28001]` | `TestGetPrimaryContainerPorts::test_flow_id_0` |
| `get_primary_container_ports(1)` returns `[28002, 28003]` | `TestGetPrimaryContainerPorts::test_flow_id_1` |
| `get_primary_container_ports(1000)` wraps around | `TestGetPrimaryContainerPorts::test_flow_id_1000_wraps_around` |
| Port uniqueness: 100 consecutive | `TestPortUniqueness::test_unique_port_pairs` |
| Constants match PentAGI | `TestConstants::test_*` (4 testes) |

---

## Diagrama de Dependencias

```
US-019 (utils.py)           <-- este story
  |
  +-- US-013 (DockerClient)
  |     |
  |     +-- US-014a (Image Management)
  |     |     |
  |     |     +-- US-014b (Container Creation)
  |     |           |
  |     |           +-- US-015 (Exec)
  |     |           +-- US-016 (File Ops)
  |     |           +-- US-017 (Stop/Remove)
  |     |                 |
  |     |                 +-- US-018 (Cleanup)
```

Todos os stories subsequentes importam constantes ou funcoes deste modulo.

---

## Related Notes

- [Docs Home](../../README.md)
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[US-013-DOCKER-CLIENT-EXPLAINED]]
- [[US-014A-IMAGE-MANAGEMENT-EXPLAINED]]
