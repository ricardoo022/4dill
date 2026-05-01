---
tags: [docker]
---

# US-015: Container Exec (Command Execution) — Explicacao Detalhada

Esta nota documenta as alteracoes feitas em `src/pentest/docker/client.py`, `src/pentest/models/tool_args.py`, `src/pentest/tools/terminal.py`, `tests/integration/docker/test_client.py`, `tests/unit/docker/test_client.py` e `tests/unit/tools/test_terminal_file.py` para implementar execucao de comandos em containers com timeout, detach, sanitizacao de output e validacao de estado.

---

## Contexto

A US-015 fecha a lacuna entre o tool de terminal e o runtime Docker: o scanner/orchestrator precisa de executar comandos reais no sandbox e receber output robusto mesmo quando comandos bloqueiam, retornam bytes invalidos, ou correm em background.

- O `DockerClient` ja criava containers, mas faltava executar comandos dentro deles.
- O terminal tool precisava de defaults alinhados com a story (`300s`, max `1200s`).
- Era necessario suportar dois modos operacionais: bloqueante e detached.
- O output precisa ser seguro para serializacao LLM/UI (UTF-8 invalido nao pode quebrar o loop).
- Os testes foram divididos em unit (ramificacoes internas) e integration (Docker real) para prova forte em CI.

---

## Referencia PentAGI (Go)

US-015 referencia `terminal.go` (ExecCommand/getExecResult) no PentAGI. A implementacao Python segue a mesma intencao:

- validar container ativo antes de exec;
- criar exec com shell (`sh -c`);
- ler stream com timeout;
- retornar output parcial + hint em timeout;
- suportar detach com quick-check.

Porque e assim?

O loop autonomo de agentes nao pode bloquear indefinidamente num comando longo, mas tambem nao pode perder o resultado quando o comando termina rapidamente. O quick-check de 500ms e um equilibrio entre latencia e confiabilidade operacional.

---

## `is_container_running` e `exec_command` (`src/pentest/docker/client.py`)

```python
def is_container_running(self, container_id: str) -> bool:
    """Return True when the container is running and healthy.

    A container without a health check is considered healthy when running.
    """
    try:
        container = self._client.containers.get(container_id)
        container.reload()
    except docker.errors.NotFound:
        return False
    except docker.errors.DockerException:
        return False

    state = container.attrs.get("State", {})
    if state.get("Status") != "running":
        return False

    health = state.get("Health")
    if health is None:
        return True
    return health.get("Status") == "healthy"
```

| Linha(s) | Explicacao |
|---|---|
| `try/except` | Trata `NotFound`/erros Docker como `False` (check idempotente, sem excecao para fluxo normal). |
| `container.reload()` | Garante estado fresco antes de inspecao. |
| `State.Status` | Exige `running` como pre-condicao. |
| `State.Health` | Se existir healthcheck, exige `healthy`; sem healthcheck, `running` basta. |

```python
def exec_command(
    self,
    container_id: str,
    command: str,
    cwd: str = WORK_FOLDER_PATH,
    timeout: int = 300,
    detach: bool = False,
) -> str:
    """Execute a shell command inside a container and return combined output."""
    if not self.is_container_running(container_id):
        raise RuntimeError(f"Container {container_id!r} is not running or healthy")

    effective_timeout = min(max(timeout, 1), 1200)
    workdir = cwd or WORK_FOLDER_PATH
    exec_cfg = self._client.api.exec_create(
        container=container_id,
        cmd=["sh", "-c", command],
        stdout=True,
        stderr=True,
        tty=True,
        workdir=workdir,
    )
    exec_id = exec_cfg["Id"]
```

| Parametro | Tipo | Default/Regra | Explicacao |
|---|---|---|---|
| `container_id` | `str` | obrigatorio | Container alvo para exec. |
| `command` | `str` | obrigatorio | Comando shell corrido via `sh -c`. |
| `cwd` | `str` | `/work` | Diretoria de trabalho (fallback para `/work` quando vazio). |
| `timeout` | `int` | `300`, clamp `1..1200` | Timeout efetivo usado na leitura de stream. |
| `detach` | `bool` | `False` | Alterna modo bloqueante vs quick-check background. |

```python
def _read_exec(exec_ref: str, max_seconds: float) -> tuple[str, bool]:
    stream = self._client.api.exec_start(exec_ref, tty=True, socket=True)
    chunks: list[bytes] = []
    timed_out = False
    deadline = time.monotonic() + max_seconds
    raw_stream = getattr(stream, "_sock", stream)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break

            raw_stream.settimeout(min(0.2, remaining))
            try:
                chunk = raw_stream.recv(4096)
            except socket.timeout:
                continue

            if not chunk:
                break
            chunks.append(chunk)
    finally:
        with contextlib.suppress(Exception):
            stream.close()

    return b"".join(chunks).decode("utf-8", errors="replace"), timed_out
```

Passo-a-passo:

1. Abre o socket de exec em modo TTY com `socket=True` para leitura incremental.
2. Define `deadline` monotonic para evitar problemas com clock do sistema.
3. Faz polling curto (`<=200ms`) para equilibrar responsividade e custo de loop.
4. Agrega chunks binarios e decodifica com `errors="replace"` (sanitizacao UTF-8).
5. Fecha stream em `finally`, suprimindo erros de close.

```python
if detach:
    output_text, timed_out = _read_exec(exec_id, 0.5)
    inspect = self._client.api.exec_inspect(exec_id)
    if timed_out or inspect.get("Running"):
        return "Command started in background"

    if output_text:
        return output_text

    if inspect.get("ExitCode", 0) == 0:
        return "Command completed successfully with exit code 0"
    return f"Command failed with exit code {inspect.get('ExitCode')}"

output_text, timed_out = _read_exec(exec_id, float(effective_timeout))

inspect = self._client.api.exec_inspect(exec_id)
if timed_out or inspect.get("Running", False):
    partial = output_text[:500]
    if len(output_text) > 500:
        partial += "..."
    timeout_message = (
        f"\nCommand timed out after {effective_timeout}s. "
        "Try detached mode for long-running commands."
    )
    return f"{partial}{timeout_message}" if partial else timeout_message.strip()
```

Fluxo de controlo:

```text
            +-----------------------+
            | exec_command(...)     |
            +-----------+-----------+
                        |
                        v
            +-----------------------+
            | is_container_running? |
            +-----+-----------+-----+
                  |           |
                 no          yes
                  |           |
                  v           v
          RuntimeError    +----------------+
                          | detach == True?|
                          +----+-------+---+
                               |       |
                              yes     no
                               |       |
                               v       v
                       read 0.5s   read timeout
                               |       |
                               v       v
                      running? msg   timeout?
                               |       |
                               v       v
                           background partial+hint
```

Porque e assim?

O timeout bloqueante devolve output parcial truncado (500 chars) para manter utilidade diagnostica sem estourar contexto do agente. O modo detached devolve mensagem imediata quando o processo continua a correr, evitando deadlocks no ciclo autonomo.

---

## `TerminalAction` timeout default (`src/pentest/models/tool_args.py`)

```python
class TerminalAction(BaseModel):
    """Schema for terminal tool calls."""

    input: str = Field(..., description="Command to execute")
    cwd: str = Field("/work", description="Working directory")
    detach: bool = Field(False, description="Run in background")
    timeout: int = Field(300, ge=10, le=1200, description="Timeout in seconds")
    message: str = Field(..., description="Human-facing description of the command")
```

| Campo | Tipo | Default/Constraint | Explicacao |
|---|---|---|---|
| `input` | `str` | obrigatorio | Comando terminal. |
| `cwd` | `str` | `/work` | Diretoria de execucao no container. |
| `detach` | `bool` | `False` | Execucao em background. |
| `timeout` | `int` | `300`, `ge=10`, `le=1200` | Alinhado com US-015 (5 min default, 20 min max). |
| `message` | `str` | obrigatorio | Texto humano para auditoria do tool call. |

---

## `create_terminal_tool` defaults (`src/pentest/tools/terminal.py`)

```python
@tool(args_schema=TerminalAction)
def terminal(
    input: str,
    cwd: str = "/work",
    detach: bool = False,
    timeout: int = 300,
    message: str = "",
) -> str:
    try:
        return docker_client.exec_command(container_id, input, cwd, timeout, detach)
    except Exception as e:
        return f"terminal tool error: {e}"
```

```python
@tool(args_schema=TerminalAction)
def terminal(
    input: str,
    cwd: str = "/work",
    detach: bool = False,
    timeout: int = 300,
    message: str = "",
) -> str:
    return f"Mock terminal executed: {input}"
```

| Linha(s) | Explicacao |
|---|---|
| `timeout=300` | Sincroniza wrapper com schema `TerminalAction` para nao haver defaults divergentes. |
| `except Exception` | Preserva loop de agente: erro vira string, nao excecao fatal no grafo. |

---

## Testes de Integracao US-015 (`tests/integration/docker/test_client.py`)

```python
@pytest.mark.integration
def test_exec_command_basic_and_stderr_capture(...):
    ok_output = file_client.exec_command(running_container.id, "echo hello", timeout=5)
    assert "hello" in ok_output

    err_output = file_client.exec_command(running_container.id, "ls /nonexistent", timeout=5)
    assert "No such file" in err_output or "cannot access" in err_output
```

```python
@pytest.mark.integration
def test_exec_command_timeout_output_is_truncated_to_500_chars(...):
    long_running_output = file_client.exec_command(
        running_container.id,
        "yes A | tr -d '\\n' | head -c 700; sleep 10",
        timeout=1,
    )

    rendered_output, timeout_hint = long_running_output.split("\nCommand timed out after 1s", maxsplit=1)
    assert rendered_output.endswith("...")
    assert len(rendered_output[:-3]) == 500
```

```python
@pytest.mark.integration
def test_exec_command_timeout_uses_max_timeout_clamp_in_hint(...):
    monotonic_values = [0.0, 1301.0, 1302.0]

    def _fake_monotonic() -> float:
        if monotonic_values:
            return monotonic_values.pop(0)
        return 1302.0

    with patch("pentest.docker.client.time", SimpleNamespace(monotonic=_fake_monotonic)):
        output = file_client.exec_command(running_container.id, "sleep 60", timeout=9999)

    assert "Command timed out after 1200s" in output
```

| Teste | Prova de criterio |
|---|---|
| `test_is_container_running_true_for_running_container` | `is_container_running == True` quando container esta ativo. |
| `test_is_container_running_false_for_stopped_container` | `is_container_running == False` quando container para. |
| `test_exec_command_basic_and_stderr_capture` | stdout/stderr combinado em comandos reais. |
| `test_exec_command_timeout_and_detach_mode` | timeout bloqueante + mensagem detached. |
| `test_exec_command_workdir_defaults_and_custom` | `cwd` default `/work` e custom `/tmp`. |
| `test_exec_command_empty_output_and_invalid_utf8` | mensagem de sucesso em output vazio + sanitizacao UTF-8. |
| `test_exec_command_timeout_output_is_truncated_to_500_chars` | truncacao de output parcial para 500 chars. |
| `test_exec_command_timeout_uses_max_timeout_clamp_in_hint` | clamp de timeout max para `1200s`. |

Nota adicional da diff:

```python
container.exec_run(["sh", "-c", "mkdir -p /work"])
```

Esta linha no fixture `running_container` reduz flakes: garante que o `cwd` default existe no container de teste.

---

## Testes Unitarios de ramificacoes internas (`tests/unit/docker/test_client.py`)

```python
def test_is_container_running_false_when_unhealthy(...):
    container.attrs = {"State": {"Status": "running", "Health": {"Status": "unhealthy"}}}
    assert docker_client_for_files.is_container_running("cid-1") is False
```

```python
def test_exec_command_timeout_returns_partial_and_hint(...):
    with patch("pentest.docker.client.time.monotonic", side_effect=[0.0, 0.1, 3.0]):
        result = docker_client_for_files.exec_command("cid-1", "sleep 10", "/work", 2, False)
    assert "partial output" in result
    assert "Command timed out after 2s" in result
```

| Grupo | Cobertura |
|---|---|
| `is_container_running_*` | Health/no-health/not-found sem custo de daemon real. |
| `exec_command_returns_output_for_success` | caminho feliz com stream fechado. |
| `exec_command_returns_success_message_on_empty_output` | fallback de sucesso sem stdout/stderr. |
| `exec_command_timeout_returns_partial_and_hint` | branch de timeout em blocking mode. |
| `exec_command_detach_returns_background_message` | branch de detach com processo ainda running. |
| `exec_command_clamps_timeout_to_max_1200` | clamp max em comportamento deterministico. |

---

## Teste de schema/wrapper (`tests/unit/tools/test_terminal_file.py`)

```python
default_timeout = TerminalAction(input="pwd", message="default")
assert default_timeout.timeout == 300
```

Este teste impede regressao de defaults inconsistentes entre schema e wrapper terminal.

---

## Exemplo Completo

```text
Step 1: Agent chama tool terminal com input="nmap --version", sem timeout explicito
  -> input: {cwd: "/work", detach: false, timeout: (omitido)}
  -> output: schema aplica timeout=300

Step 2: Wrapper chama DockerClient.exec_command(...)
  -> input: container_id + command + timeout=300
  -> output: cria exec Docker com ["sh", "-c", command]

Step 3: Runtime le stream
  -> se terminar: devolve stdout/stderr combinado
  -> se timeout: devolve parcial (max 500) + hint para detach

Step 4: Agent recebe string final
  -> output: texto seguro UTF-8 (bytes invalidos substituidos)
```

---

## Questoes Frequentes

### P: Porque `is_container_running` exige `healthy` quando existe healthcheck?

A: Porque `running` sozinho nao garante prontidao funcional. Se a imagem define healthcheck, usar esse sinal evita executar ferramentas enquanto o runtime ainda esta a inicializar.

### P: Porque truncar para 500 chars no timeout?

A: Evita inundar contexto do agente com logs enormes, mantendo ainda uma amostra util para debug.

### P: Porque o teste de clamp em integracao usa patch de `time.monotonic`?

A: Sem patch, provar clamp para `1200s` exigiria esperar 20 minutos. O patch mantem execucao rapida e valida a mensagem final do comportamento de timeout efetivo.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/docker/client.py` | Implementa `is_container_running` e `exec_command` com timeout/detach/sanitizacao/truncacao. |
| `src/pentest/models/tool_args.py` | Atualiza default de `TerminalAction.timeout` para `300`. |
| `src/pentest/tools/terminal.py` | Alinha defaults do wrapper terminal e mock terminal para `300`. |
| `tests/integration/docker/test_client.py` | Provas em Docker real para todos os criterios da US-015. |
| `tests/unit/docker/test_client.py` | Cobertura deterministica das ramificacoes internas de exec. |
| `tests/unit/tools/test_terminal_file.py` | Regressao do default de timeout no schema. |

---

## Related Notes

- [Docs Home](../../README.md)
- [[USER-STORIES]]
- [[PROJECT-STRUCTURE]]
- [[EXECUTION-FLOW]]
- [[US-014B-CONTAINER-CREATION-STARTUP-EXPLAINED]]
