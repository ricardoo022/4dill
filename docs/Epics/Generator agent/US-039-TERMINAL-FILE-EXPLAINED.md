---
tags: [agents, docker]
---

# US-039: Terminal & File Tools — Explicacao Detalhada

Este documento explica o padrão de **Factory com Closures** usado em `src/pentest/tools/terminal.py` e `src/pentest/tools/file.py`. Estas ferramentas necessitam acesso ao Docker client e container ID, o que torna imperativo usar injecção de dependências via closures.

---

## Contexto: Por que Factory Functions?

Em US-037 e US-038, vimos que barrier tools sao decoradas com `@tool` a nivel de modulo:

```python
# Nao funciona para tools com estado!
@tool(args_schema=SubtaskList)
def subtask_list(subtasks: list, message: str) -> str:
    return f"ok"
```

Mas as ferramentas de execucao (`terminal`, `file`) necessitam de **estado externo**: o Docker client e container ID. Nao podem ser top-level porque nao temos acesso a essas variaveis no momento de carregamento do modulo.

**Solucao**: Factory functions que retornam tools personalizadas com dependências injectadas via closure.

```python
def create_terminal_tool(docker_client: Any, container_id: str) -> BaseTool:
    @tool(args_schema=TerminalAction)
    def terminal(input: str, cwd: str = "/work", ...) -> str:
        # docker_client e container_id vem da closure
        return docker_client.exec_command(container_id, input, ...)
    return terminal
```

---

## Arquitectura: Terminal Tool

Ficheiro: `src/pentest/tools/terminal.py`

### Factory: create_terminal_tool()

```python
def create_terminal_tool(docker_client: Any, container_id: str) -> BaseTool:
    """Create a terminal tool that executes commands inside the given container.

    The returned object is a LangChain StructuredTool. All exceptions are caught
    and returned as strings so the agent loop never raises.
    """

    @tool(args_schema=TerminalAction)
    def terminal(
        input: str,  # noqa: A002
        cwd: str = "/work",
        detach: bool = False,
        timeout: int = 60,
        message: str = "",
    ) -> str:
        """Execute a command inside the provided Docker container using the injected client."""
        try:
            return docker_client.exec_command(container_id, input, cwd, timeout, detach)  # type: ignore[no-any-return]
        except Exception as e:
            return f"terminal tool error: {e}"

    return terminal
```

### Assinatura da Factory

| Parametro | Tipo | Proposito |
|---|---|---|
| `docker_client` | `Any` | Client Docker (injectado pela camada de infra) |
| `container_id` | `str` | ID do container onde executar comandos |
| **Retorna** | `BaseTool` | Tool LangChain compilada e pronta |

### Closure: Como Funciona

#### Passo 1: Factory recebe dependências

```python
docker_client = docker.from_env()  # Em tempo de execucao
container_id = "abc123xyz"

tool = create_terminal_tool(docker_client, container_id)
```

#### Passo 2: Factory define a funcao interna

```python
@tool(args_schema=TerminalAction)
def terminal(...):
    # Este escopo tem acesso a docker_client e container_id
    # da closure (do escopo da factory)
    return docker_client.exec_command(container_id, input, ...)
```

#### Passo 3: Factory retorna a tool compilada

```python
return terminal  # BaseTool ja compilada com @tool
```

#### Passo 4: Agent usa a tool

```python
agent = create_agent_graph(
    llm=...,
    tools=[tool],  # Ja contem docker_client + container_id
    barrier_names={...}
)

result = agent.invoke({...})
# Quando LLM chamar terminal("ls"), a closure tem acesso ao docker_client
```

### Diagrama de Escopo

```
┌─ create_terminal_tool(docker_client, container_id)
│
├─ docker_client: Docker           ← Recebida como argumento
├─ container_id: str               ← Recebida como argumento
│
├─ @tool(args_schema=TerminalAction)
│  def terminal(input, cwd, ...):
│     ↓
│     Acesso à closure:
│     - docker_client ✓
│     - container_id ✓
│     - Parametros locais: input, cwd, ...
│     ↓
│     return docker_client.exec_command(...)
│
└─ return terminal  # BaseTool com closure capturada
```

### Tratamento de Erros

```python
try:
    return docker_client.exec_command(container_id, input, cwd, timeout, detach)
except Exception as e:
    return f"terminal tool error: {e}"
```

**Politica**: Nunca raise exceptions ao agent loop. Sempre retornar strings. Isso permite ao LLM ver o erro e reagir (retry, escolher outra tool, etc.).

### Type Ignore para Mypy

```python
return docker_client.exec_command(...)  # type: ignore[no-any-return]
```

O `docker_client` tem tipo `Any` (tipo dinamico desconhecido). Mypy reclamaria. A anotacao `# type: ignore[no-any-return]` diz a Mypy: "Confia, isto e um return string valido".

---

## Questao Critica: Shadowing ("command" vs "input")

### O Problema Original

Em PentAGI (Go), o parametro chama-se `command`:

```go
// PentAGI (Go)
type TerminalAction struct {
    Command string
    CWD     string
    Detach  bool
    Timeout int
}

func (a *TerminalAction) Handle() string {
    return docker.ExecCommand(a.Command, a.CWD, a.Timeout, a.Detach)
}
```

Mas em Python 3.12, `command` e uma keyword built-in (quase). Usar como nome de parametro gera warning de Ruff:

```python
def terminal(command: str, ...):  # ← Ruff warning: "A002: argument shadows Python built-in"
    pass
```

### A Solucao

Renomeamos para `input`:

```python
from typing import Any

def terminal(
    input: str,  # Sem warnings, mais Python-idiomatic
    cwd: str = "/work",
    ...
) -> str:
```

Mas para manter compatibilidade com PentAGI (em caso de futuro cross-platforming), adicionamos um comentario Ruff:

```python
def terminal(
    input: str,  # noqa: A002
    ...
):
```

O `# noqa: A002` significa: "Ruff, ignora o warning A002 (built-in shadowing) nesta linha".

**Porque isto nao e um problema real?** Porque:

1. `input` e um built-in (a funcao `input()` para ler do stdin)
2. Mas ao usar como parametro, shadowing e local (nao afeta o built-in globalmente)
3. Eh uma pratica comum em Python — a maioria dos linters aceita isto
4. Ruff e conservador, por isso o `# noqa`

### Compatibilidade com PentAGI

PentAGI usa `command`, mas o nosso schema Pydantic usa `input`:

**schema** (`tool_args.py`):

```python
class TerminalAction(BaseModel):
    input: str = Field(..., description="Command to execute")
```

**O LLM ve**:

```json
{
  "tool": "terminal",
  "parameters": {
    "input": "nmap 10.0.0.1",
    "cwd": "/work",
    ...
  }
}
```

Quando o PentAGI Go chamar a tool Python via RPC (futuro), tera que mapear `Command` → `input`. Mas agora, dentro da suite Python, usamos `input` (Pythonic).

---

## Arquitectura: File Tool

Ficheiro: `src/pentest/tools/file.py`

### Factory: create_file_tool()

```python
def create_file_tool(docker_client: Any, container_id: str) -> BaseTool:
    """Create a file tool that reads or updates files inside the given container.

    All exceptions are caught and returned as strings so the agent loop never raises.
    """

    @tool(args_schema=FileAction)
    def file(action: str, path: str, content: str | None = None, message: str = "") -> str:
        """Perform file operations inside the container: read or update files."""
        try:
            if action == "read_file":
                return docker_client.read_file(container_id, path)  # type: ignore[no-any-return]
            if action == "update_file":
                return docker_client.write_file(container_id, path, content or "")  # type: ignore[no-any-return]
            return f"file tool error: unknown action {action}"
        except Exception as e:
            return f"file tool error: {e}"

    return file
```

### Schema: FileAction

```python
class FileAction(BaseModel):
    action: Literal["read_file", "update_file"] = Field(..., description="File action to perform")
    path: str = Field(..., min_length=1, description="Path inside the container")
    content: str | None = Field(None, description="Content to write for update_file")
    message: str = Field(..., description="Short internal description for logs and agent handoff")
```

### Multiplex de Acoes

Ao contrario do terminal que faz uma coisa (executar comando), o file tool faz **duas coisas** multiplexadas:

| Acao | Input | Output | Funcao Docker |
|---|---|---|---|
| `read_file` | `path` | Conteudo do ficheiro | `docker_client.read_file(container_id, path)` |
| `update_file` | `path`, `content` | Confirmacao | `docker_client.write_file(container_id, path, content)` |

#### Logica de Dispatch

```python
if action == "read_file":
    return docker_client.read_file(container_id, path)
if action == "update_file":
    return docker_client.write_file(container_id, path, content or "")
return f"file tool error: unknown action {action}"
```

Se `action` nao for reconhecido, retorna erro (nao raise exception).

#### Exemplo de Chamada do LLM

```
[Turno 1]
LLM: "Quero ver o ficheiro /etc/hosts"
tool_calls: [{
    "name": "file",
    "args": {
        "action": "read_file",
        "path": "/etc/hosts",
        "content": None,
        "message": "Read hosts file"
    }
}]

File tool executa:
  if action == "read_file":  # SIM
      return docker_client.read_file(container_id, "/etc/hosts")
  # Retorna conteudo

[Turno 2]
LLM: "Vou atualizar o ficheiro /tmp/config.txt"
tool_calls: [{
    "name": "file",
    "args": {
        "action": "update_file",
        "path": "/tmp/config.txt",
        "content": "new config content",
        "message": "Update config"
    }
}]

File tool executa:
  if action == "update_file":  # SIM
      return docker_client.write_file(container_id, "/tmp/config.txt", "new config...")
  # Retorna confirmacao
```

### Validacao Pydantic

```python
class FileAction(BaseModel):
    action: Literal["read_file", "update_file"]  # OBRIGADO ser um dos dois
    path: str = Field(..., min_length=1)          # OBRIGADO ter >= 1 caracter
    content: str | None = None                    # OPCIONAL (None para read_file)
```

Se o LLM tenta:
- `action="invalid"` → Pydantic error (LangChain ve e retorna erro ao LLM)
- `path=""` → Pydantic error (path vazio invalido)
- `path="/tmp/file"`, `action="read_file"` → OK (content ignorado)

---

## Mock Strategy: Testes sem Docker

### create_mock_terminal_tool()

```python
def create_mock_terminal_tool() -> BaseTool:
    @tool(args_schema=TerminalAction)
    def terminal(
        input: str,  # noqa: A002
        cwd: str = "/work",
        detach: bool = False,
        timeout: int = 60,
        message: str = "",
    ) -> str:
        """Mock terminal implementation that returns a predictable string for tests."""
        return f"Mock terminal executed: {input}"

    return terminal
```

### create_mock_file_tool()

```python
def create_mock_file_tool() -> BaseTool:
    @tool(args_schema=FileAction)
    def file(action: str, path: str, content: str | None = None, message: str = "") -> str:
        """Mock file tool for tests; returns predictable messages for read/update."""
        if action == "read_file":
            return f"Mock read from {path}"
        if action == "update_file":
            return f"Mock updated {path} with {len(content or '')} bytes"
        return f"file tool error: unknown action {action}"

    return file
```

### Proposito

Permite testes do agent loop **sem necessidade de Docker** em tempo de desenvolvimento:

#### Cenario 1: Desenvolvimento Local (Mock)

```python
# tests/unit/test_generator.py
from pentest.tools.terminal import create_mock_terminal_tool
from pentest.tools.file import create_mock_file_tool

def test_generator_agent():
    generator = create_agent_graph(
        llm=mock_llm,
        tools=[
            create_mock_terminal_tool(),  # Nao precisa Docker
            create_mock_file_tool(),
        ],
        barrier_names={"subtask_list"}
    )

    result = generator.invoke({"messages": [...]})
    assert result["barrier_hit"] is True
```

#### Cenario 2: Producao (Real Docker)

```python
# main.py
from docker import Docker
from pentest.tools.terminal import create_terminal_tool
from pentest.tools.file import create_file_tool

docker_client = Docker.from_env()
container = docker_client.containers.run("kali:latest", ...)

generator = create_agent_graph(
    llm=ChatAnthropic(...),
    tools=[
        create_terminal_tool(docker_client, container.id),  # Com Docker
        create_file_tool(docker_client, container.id),
    ],
    barrier_names={"subtask_list"}
)

result = generator.invoke({"messages": [...]})
```

### Vantagens

| Aspecto | Mock | Real |
|---|---|---|
| Setup | Instantaneo | Precisa Docker running |
| Velocidade | Muito rapido | Mais lento (I/O Docker) |
| Uso | Unit tests, CI | E2E tests, producao |
| Determinismo | Sempre retorna mesmo | Depende do container |

---

## Uso na Pratica: End-to-End

### Cenario: Generator Agent

```python
# setup.py ou main.py
from docker import Docker
from langchain_anthropic import ChatAnthropic
from pentest.agents.base import create_agent_graph
from pentest.tools.terminal import create_terminal_tool
from pentest.tools.file import create_file_tool
from pentest.tools.browser import create_browser_tool
from pentest.tools.barriers import subtask_list

# Inicializar Docker
docker_client = Docker.from_env()
container = docker_client.containers.run(
    "kali:latest",
    command="sleep 3600",
    detach=True
)

# Criar tools com dependencias injectadas
terminal_tool = create_terminal_tool(docker_client, container.id)
file_tool = create_file_tool(docker_client, container.id)
browser_tool = create_browser_tool()

# Criar agent
generator = create_agent_graph(
    llm=ChatAnthropic(model="claude-sonnet-4-5"),
    tools=[terminal_tool, file_tool, browser_tool, subtask_list],
    barrier_names={"subtask_list"},
    max_iterations=20,
)

# Usar agent
from langchain_core.messages import SystemMessage, HumanMessage

result = generator.invoke({
    "messages": [
        SystemMessage("Tu es o Generator. Analisa o target e cria um plano de pentest."),
        HumanMessage("Target: 10.0.0.1, scope: web app com autenticacao"),
    ]
})

# Extrair resultado
plan = result["barrier_result"]
print(f"Plano com {len(plan['subtasks'])} subtasks:")
for subtask in plan["subtasks"]:
    print(f"  - {subtask['title']}: {subtask['description']}")
```

### Fluxo Interno: 3 Turnos

```
[Turno 1]
LLM: "Vou fazer reconnaissance. Primeiro, um nmap."
tool_calls: [{
    "name": "terminal",
    "args": {"input": "nmap -A 10.0.0.1", "cwd": "/work", ...}
}]

BarrierAwareToolNode:
  - Executa: docker_client.exec_command(container_id, "nmap -A 10.0.0.1", ...)
  - Retorna: ToolMessage("PORT 22 open, PORT 80 open...")
  - Verifica: "terminal" in {"subtask_list"}? NAO
  - barrier_hit = False → volta a call_llm

[Turno 2]
LLM: "Vi que nginx 1.18 esta aberto. Vou verificar se ha ficheiros de config."
tool_calls: [{
    "name": "file",
    "args": {"action": "read_file", "path": "/etc/nginx/nginx.conf", ...}
}]

BarrierAwareToolNode:
  - Executa: docker_client.read_file(container_id, "/etc/nginx/nginx.conf")
  - Retorna: ToolMessage("http { server { listen 80; ...")
  - Verifica: "file" in {"subtask_list"}? NAO
  - barrier_hit = False → volta a call_llm

[Turno 3]
LLM: "Ja tenho informacao. Criei o plano:"
tool_calls: [{
    "name": "subtask_list",
    "args": {
        "subtasks": [
            {"title": "Scan ports", "description": "nmap -A", "fase": "recon"},
            {"title": "Check nginx CVEs", "description": "nuclei", "fase": "research"},
            {"title": "Test auth bypass", "description": "manual testing", "fase": "exploitation"}
        ],
        "message": "Initial plan ready"
    }
}]

BarrierAwareToolNode:
  - Executa: subtask_list(...) → "subtask list successfully processed..."
  - Verifica: "subtask_list" in {"subtask_list"}? SIM ✓
  - barrier_result = args (subtasks + message)
  - barrier_hit = True → END

Agent Termina
result["barrier_result"] = {
    "subtasks": [...],
    "message": "Initial plan ready"
}
```

---

## Testes: Como Sao Validados

Ficheiro: `tests/unit/tools/test_terminal_file.py`

### Validacao de Schema

```python
def test_terminal_action_validation():
    # FALHA: timeout < 10
    with pytest.raises(ValidationError):
        TerminalAction(input="ls", timeout=5, message="msg")

    # SUCESSO: timeout valido
    ta = TerminalAction(input="ls -la", timeout=10, message="run list")
    assert ta.input == "ls -la"
    assert ta.timeout == 10
```

Pydantic valida: `timeout` tem restricoes `ge=10, le=1200`.

### Teste da Factory com Mock Docker

```python
def test_terminal_factory_with_mock_docker():
    # Setup mock
    mock_docker = MagicMock()
    mock_docker.exec_command.return_value = "real container output"

    # Criar tool com mock
    tool = create_terminal_tool(mock_docker, "container-1")

    # Invocar
    res = tool.run({
        "input": "whoami",
        "cwd": "/work",
        "detach": False,
        "timeout": 60,
        "message": "t"
    })

    # Validar
    assert res == "real container output"
    mock_docker.exec_command.assert_called_once_with(
        "container-1", "whoami", "/work", 60, False
    )
```

**O que valida:**
- Factory cria tool funcional ✓
- Closure captura docker_client e container_id ✓
- Tool chama docker_client.exec_command com parametros corretos ✓
- Return value e o resultado da chamada ✓

### Teste de Error Handling

```python
def test_terminal_factory_with_mock_docker():
    # ...

    # Simular exception
    mock_docker.exec_command.side_effect = Exception("boom")
    res2 = tool.run({
        "input": "bad",
        "cwd": "/work",
        "detach": False,
        "timeout": 60,
        "message": "t"
    })

    # Validar que erro e retornado como string (nao raise)
    assert isinstance(res2, str) and "terminal tool error" in res2
```

**O que valida:**
- Exceptions sao catchadas ✓
- Erros retornados como strings ✓
- Nunca raise ao agent loop ✓

---

## Comparacao com Padroes Alternativos

### Alternativa 1: Top-level Function (INCORRETO)

```python
# NAO FUNCIONA: docker_client nao definido em scope global
@tool(args_schema=TerminalAction)
def terminal(input: str, cwd: str = "/work", ...) -> str:
    return docker_client.exec_command(...)  # NameError: docker_client nao definido
```

**Problema**: `docker_client` soh existe em tempo de execucao, nao em tempo de carregamento do modulo.

### Alternativa 2: Global Singleton (FRAGIL)

```python
# Fragil: estado global partilhado
DOCKER_CLIENT = None
CONTAINER_ID = None

def set_docker_context(client, container_id):
    global DOCKER_CLIENT, CONTAINER_ID
    DOCKER_CLIENT = client
    CONTAINER_ID = container_id

@tool(args_schema=TerminalAction)
def terminal(input: str, ...) -> str:
    return DOCKER_CLIENT.exec_command(CONTAINER_ID, ...)  # Depende de global
```

**Problema**: Estado global e dificil de testar, pode ter race conditions em concorrencia.

### Alternativa 3: Factory com Closure (CORRETO)

```python
# Limpo: injecao de dependencias via closure
def create_terminal_tool(docker_client, container_id):
    @tool(args_schema=TerminalAction)
    def terminal(input: str, ...) -> str:
        return docker_client.exec_command(container_id, ...)
    return terminal
```

**Vantagens**:
- Dependencias explicitas (argumentos da factory)
- Facil de testar (mock passado como argumento)
- Soh em uso quando necessario
- Nao ha estado global

---

## Resumo: Padroes e Decisoes

| Decisao | Razao | Impacto |
|---|---|---|
| **Factory Pattern** | Tools precisam acesso a Docker client | Criar tools dinamicamente, nunca globalmente |
| **Closure para DI** | Python nao tem DI nativa como Go | Funcoes aninhadas capturam escopo externo |
| **`input` nao `command`** | Compatibilidade com Python 3.12, shadowing | Rename para evitar warnings (com `# noqa: A002`) |
| **File multiplexing** | Uma tool faz leitura + escrita | Dispatch baseado em `action` field |
| **Mock factories** | Testes sem Docker | Rapid feedback loop em dev |
| **Error strings** | Nunca raise ao agent loop | LLM ve erros e reage apropriadamente |

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-037-BASE-GRAPH-EXPLAINED]] — StateGraph, BarrierAwareToolNode
- [[US-038-BARRIERS-EXPLAINED]] — Barrier tools e modelo de terminacao
- [[US-040-BROWSER-TOOL-EXPLAINED]] — Tool HTTP usada no mesmo conjunto base do Generator
- [[EXECUTION-FLOW]] — Contexto de quando estas tools entram no ciclo de execução
- **src/pentest/agents/base.py** — Implementacao do agent graph
- **src/pentest/tools/terminal.py** — Code completo
- **src/pentest/tools/file.py** — Code completo
- **src/pentest/models/tool_args.py** — Schemas Pydantic
- **tests/unit/tools/test_terminal_file.py** — Testes e exemplos de uso
