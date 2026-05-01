---
tags: [agents]
---

# US-044: Generator Agent Completo — Explicacao Detalhada

Este documento explica a implementacao do Generator agent funcional, que integra o base graph (US-037), as tools (US-038 a US-041), o skill index (US-042) e o prompt renderer (US-043) num unico entry point chamavel pelo controller. Os ficheiros explicados sao `src/pentest/agents/generator.py`, `src/pentest/agents/__init__.py`, `tests/agent/test_generator_agent.py`, `tests/unit/agents/test_generator.py` e `tests/e2e/test_generator_claude_e2e.py`.

---

## Contexto

O Generator e o primeiro agente a executar no ciclo de vida de um scan. A sua responsabilidade e produzir um plano estruturado de subtasks (1 a 15) a partir de um alvo e do resultado da deteccao de backend (FASE 0). Esta US liga todos os componentes construidos nas USs anteriores num agente funcional:

- Recebe `input` (string descritiva do alvo), `BackendProfile` (resultado da deteccao de backend), `skills_dir` (directorio com FASE skills) e opcionalmente um `DockerClient`.
- Carrega o indice de FASE skills relevantes para o `scan_path` do perfil.
- Renderiza system + user prompt com Jinja2.
- Monta o conjunto de tools: terminal + file (se Docker disponivel), browser, memorist (stub), searcher (stub) e `subtask_list` (barrier).
- Executa o LangGraph com `ChatAnthropic` e `BarrierAwareToolNode`.
- Extrai e valida a lista de subtasks do `barrier_result`, retornando `list[SubtaskInfo]`.

Sem o Generator, o sistema nao consegue arranhar o ciclo de scan — ele e o ponto de entrada que transforma "scan https://example.com" num plano de accao estruturado.

---

## Referencia PentAGI (Go)

### `performSubtasksGenerator` (`pentagi/pkg/providers/performers.go` linhas 94-172)

O PentAGI Go executa o Generator atraves de `performSubtasksGenerator()` que:

1. Constroi o prompt com contexto do target + resultados de deteccao.
2. Chama o LLM em loop, executando tool calls ate o LLM invocar `subtasksList` (barrier).
3. Parseia o resultado JSON para `[]Subtask`.
4. Guarda a message chain na DB (`CreateMsgChain`) e logs (`putAgentLog`).

Diferencas principais na versao Python:
- **LangGraph StateGraph** substitui o loop manual do Go (`for` com reflection). O routing e declarado via `add_conditional_edges`.
- **Sem DB por agora**: o PentAGI grava `MsgChain` e `AgentLog` durante a execucao. A versao Python faz apenas `logger.info` por enquanto — a persistencia virá quando o Epic 2 (Database) for integrado no controller.
- **Barrier pattern explicito**: em vez de verificar o nome da tool no loop, o `BarrierAwareToolNode` intercepta automaticamente tools marcadas como barrier e extrai os args para `barrier_result`.
- **Limite de 15 subtasks**: o PentAGI usa `<=15` no prompt; aqui tambem se valida no codigo (`1 <= len(subtasks_raw) <= 15`).

---

## `GeneratorError` (`src/pentest/agents/generator.py` linhas 32-33)

```python
class GeneratorError(Exception):
    """Raised when the Generator cannot produce a valid subtask plan."""
```

| Elemento | Tipo | Descricao |
|---|---|---|
| `GeneratorError` | `Exception` | Erro customizado para falhas no Generator |

Excecao dedicada para que o controller possa distinguir entre "o Generator falhou" (plano invalido, barrier nao atingido, contagem errada) e erros genericos do runtime (network, LLM down, etc).

---

## Constantes de configuracao (`src/pentest/agents/generator.py` linhas 28-29)

```python
_DEFAULT_GENERATOR_MODEL = "claude-sonnet-4-20250514"
_GENERATOR_CONTAINER_ID = "generator-runtime"
```

| Constante | Valor | Razao |
|---|---|---|
| `_DEFAULT_GENERATOR_MODEL` | `"claude-sonnet-4-20250514"` | Modelo default — equilibrio entre custo e qualidade para planeamento |
| `_GENERATOR_CONTAINER_ID` | `"generator-runtime"` | ID fixo do container quando o Generator precisa de terminal/file tools |

**Porque e assim?** O `_GENERATOR_CONTAINER_ID` e hardcodado porque o Generator nao precisa de containers isolados por flow — ele corre numa instancia unica e as tools de terminal/file sao apenas para browsing/reading durante o planeamento, nao para execucao de exploits.

---

## `_resolve_generator_model` (`src/pentest/agents/generator.py` linhas 36-39)

```python
def _resolve_generator_model(model: str | None = None) -> str:
    if model:
        return model
    return os.getenv("GENERATOR_MODEL", _DEFAULT_GENERATOR_MODEL)
```

| Parametro | Tipo | Descricao |
|---|---|---|
| `model` | `str \| None` | Modelo override via parametro (prioridade maxima) |

Resolucao de modelo com cascata de 3 niveis:

1. **Parametro `model`** — se passado explicitamente, usa este (override directo)
2. **Env var `GENERATOR_MODEL`** — se definida no ambiente, usa este (configuracao do deploy)
3. **`_DEFAULT_GENERATOR_MODEL`** — fallback para `claude-sonnet-4-20250514`

Esta cascata permite testes com modelos diferentes sem alterar codigo nem variaveis de ambiente.

---

## `generate_subtasks` (`src/pentest/agents/generator.py` linhas 42-91)

Esta e a funcao principal — o entry point que o controller vai chamar.

```python
async def generate_subtasks(
    input: str,  # noqa: A002
    backend_profile: BackendProfile,
    skills_dir: str,
    docker_client: DockerClient | None = None,
    model: str | None = None,
) -> list[SubtaskInfo]:
    """Generate a penetration-testing plan as a list of validated subtasks."""
```

| Parametro | Tipo | Descricao |
|---|---|---|
| `input` | `str` | Descricao textual do alvo (ex: `"scan https://example.com"`) |
| `backend_profile` | `BackendProfile` | Perfil detectado do backend (Supabase, Firebase, Custom API) |
| `skills_dir` | `str` | Caminho para o directorio com FASE skills (SKILL.md files) |
| `docker_client` | `DockerClient \| None` | Se fornecido, inclui terminal/file tools; se `None`, so browser + stubs |
| `model` | `str \| None` | Override do modelo LLM (resolvido por `_resolve_generator_model`) |

### Passo 1: Carregar FASE index (linha 50)

```python
fase_index = load_fase_index(backend_profile.scan_path, skills_dir)
```

Usa o skill loader (US-042) para construir um indice textual das skills relevantes. O `scan_path` do `BackendProfile` indica quais FASEs sao aplicaveis ao alvo detectado (ex: `["fase-1", "fase-3"]` para Supabase).

### Passo 2: Renderizar prompts (linhas 51-56)

```python
system_prompt, user_prompt = render_generator_prompt(
    input,
    backend_profile.model_dump(),
    fase_index,
    "",
)
```

O quarto argumento (`execution_context`) e `""` porque o Generator corre isolado — nao tem contexto de execucao previo. O renderer (US-043) produz dois strings Markdown: o system prompt (instrucoes + FASE index) e o user prompt (input do utilizador).

### Passo 3: Montar tools (linhas 58-62)

```python
tools: list[Any] = []
if docker_client is not None:
    tools.append(create_terminal_tool(docker_client, _GENERATOR_CONTAINER_ID))
    tools.append(create_file_tool(docker_client, _GENERATOR_CONTAINER_ID))
tools.extend([create_browser_tool(), memorist, searcher, subtask_list])
```

O conjunto de tools depende do contexto:

| Condicao | Tools incluidas | Razao |
|---|---|---|
| `docker_client is not None` | terminal + file + browser + memorist + searcher + subtask_list | Generator pode executar comandos reais no container Kali |
| `docker_client is None` | browser + memorist + searcher + subtask_list | So ferramentas disponiveis sem container — browsing e stubs |

**Porque e assim?** O Generator pode correr em dois modos: (1) com Docker, onde pode fazer reconnaissance real com `nmap`, `curl`, etc; (2) sem Docker, onde so pode navegar por HTTP via browser tool e usar os stubs de memorist/searcher. Esta condicional evita erros quando o Docker nao esta disponivel.

### Passo 4: Criar LLM e Graph (linhas 64-69)

```python
llm = ChatAnthropic(
    model_name=_resolve_generator_model(model),
    timeout=None,
    stop=None,
)
graph = create_agent_graph(llm, tools, barrier_names={"subtask_list"}, max_iterations=20)
```

O LLM e `ChatAnthropic` com modelo resolvido pela cascata. O graph usa `barrier_names={"subtask_list"}` — so a tool `subtask_list` e considerada barrier. O `max_iterations=20` previne loops infinitos: se o LLM nao chamar `subtask_list` apos 20 iteracoes, o graph para e o codigo detecta `barrier_hit=False`.

### Passo 5: Invocar o graph (linhas 70-72)

```python
result = await graph.ainvoke(
    {"messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]}
)
```

O estado inicial contem apenas duas mensagens: o system prompt (regras + FASE index) e o user prompt (input do utilizador). O graph executa o loop `call_llm → execute_tools → call_llm → ...` ate:
- O LLM chamar `subtask_list` (barrier → `barrier_hit=True` → END)
- O LLM responder sem tool_calls (END)
- Atingir `max_iterations` (END por limite de recursao)

### Passo 6: Validar e extrair resultado (linhas 74-90)

```python
barrier_hit = bool(result.get("barrier_hit"))
barrier_result = result.get("barrier_result")
if not barrier_hit or not isinstance(barrier_result, dict):
    raise GeneratorError("Generator failed to produce a plan")

subtasks_raw = barrier_result.get("subtasks")
if not isinstance(subtasks_raw, list) or not (1 <= len(subtasks_raw) <= 15):
    raise GeneratorError("Generator failed to produce a plan")

try:
    subtasks = [SubtaskInfo.model_validate(item) for item in subtasks_raw]
except Exception as exc:
    raise GeneratorError("Generator failed to produce a plan") from exc

logger.info(
    "Generator plan created with %d subtasks: %s", len(subtasks), [s.title for s in subtasks]
)
return subtasks
```

Diagrama de validacao:

```
result
  ├── barrier_hit == False ──────────────────> raise GeneratorError
  ├── barrier_result nao e dict ─────────────> raise GeneratorError
  ├── subtasks_raw nao e list ───────────────> raise GeneratorError
  ├── len(subtasks_raw) < 1 ou > 15 ─────────> raise GeneratorError
  ├── SubtaskInfo.model_validate falha ──────> raise GeneratorError
  └── tudo valido ──────────────────────────> logger.info + return list[SubtaskInfo]
```

| Linha(s) | Validacao | Razao |
|---|---|---|
| 74-77 | `barrier_hit` deve ser `True` e `barrier_result` deve ser `dict` | O LLM tem de ter chamado `subtask_list`; caso contrario nao ha plano |
| 79-81 | `subtasks_raw` deve ser `list` com 1 a 15 elementos | Limite do PentAGI; evita planos vazios ou excessivos |
| 83-86 | Cada item deve validar como `SubtaskInfo` | Garante `title` e `description` nao vazios (field_validator do modelo) |
| 88-90 | Log com numero de subtasks e titulos | Observabilidade — o controller pode logar o plano gerado |

O `from exc` na linha 86 preserva a stack trace original para debugging, mesmo que a mensagem de erro seja generica.

---

## `__init__.py` (`src/pentest/agents/__init__.py`)

```python
"""Agent configurations: tools, limits, delegation targets per agent role."""

from pentest.agents.generator import GeneratorError, generate_subtasks

__all__ = ["GeneratorError", "generate_subtasks"]
```

Modificado de stub vazio para exportar os dois symbolos publicos do modulo Generator. Permite importacao directa:

```python
from pentest.agents import generate_subtasks, GeneratorError
```

---

## Testes — `tests/agent/test_generator_agent.py` (camada Agent)

Esta camada testa o Generator com LLM mockado mas com fluxo real de graph (via `_FakeGraph`). Os testes validam o contrato de saida e a seleccao de tools.

### `_FakeGraph` e `_FakeLLM` (linhas 14-51)

```python
class _FakeGraph:
    def __init__(self, result: dict[str, Any]):
        self._result = result

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        assert "messages" in state
        return self._result


class _FakeLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, _state):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subtask_list",
                    "args": {
                        "subtasks": [
                            {"title": "Map API surface", "description": "Enumerate public endpoints and auth requirements.", "fase": "fase-1"},
                            {"title": "Test auth bypass", "description": "Probe RLS/Auth controls on discovered endpoints.", "fase": "fase-3"},
                        ],
                        "message": "plan completed",
                    },
                    "id": "call_subtasks",
                }
            ],
        )
```

| Classe | Papel |
|---|---|
| `_FakeGraph` | Simula o graph compilado — valida que `ainvoke` recebe `messages` e retorna o resultado configurado |
| `_FakeLLM` | Simula o LLM — retorna um `AIMessage` com `tool_calls` que chamam `subtask_list` com 2 subtasks realistas de Supabase |

### `test_generate_subtasks_agent_happy_path_with_realistic_plan` (linhas 54-83)

Testa o happy path com um plano realista de Supabase (mapeamento de API surface + testes de auth). Valida:
- 1 a 15 subtasks retornadas
- Todas tem `title` e `description` nao vazios
- Pelo menos uma tem `fase` definido

### `test_generate_subtasks_toolset_selection_with_and_without_docker` (linhas 86-153)

Valida a logica condicional de tools. Executa `generate_subtasks` duas vezes:
1. **Sem Docker**: captura as tools passadas ao graph e verifica que `terminal` e `file` **nao** estao presentes.
2. **Com Docker mock**: verifica que `terminal` e `file` **estao** presentes.

```python
assert "terminal" not in captured_tools["without_docker"]
assert "file" not in captured_tools["without_docker"]
assert "terminal" in captured_tools["with_docker"]
assert "file" in captured_tools["with_docker"]
```

### `test_generate_subtasks_raises_generator_error_when_barrier_missing` (linhas 156-185)

Forca `barrier_hit=False` no resultado do graph e verifica que `GeneratorError` e levantada com a mensagem correcta:

```python
with pytest.raises(GeneratorError, match="Generator failed to produce a plan"):
    await generate_subtasks("scan https://example.com", profile, "/tmp/skills")
```

---

## Testes — `tests/unit/agents/test_generator.py` (camada Unit)

Testes mais granulares, sem dependencia de graph real — tudo via monkeypatch.

### `test_generate_subtasks_happy_path_validates_output` (linhas 32-69)

Valida que o output do Generator passa por validacao correcta:
- Subtasks com whitespace (`"  Recon  "`) sao stripped para `"Recon"` — isto e feito pelo `field_validator` do `SubtaskInfo`
- `fase=None` e aceite (subtask sem fase especifica)
- O `field_validator` rejeitaria strings vazias, mas neste teste os valores sao validos

### `test_generate_subtasks_without_docker_excludes_terminal_and_file` (linhas 72-101)

Mesma logica que o teste agent correspondente, mas com `DockerClient=None` e captura directa das tools.

### `test_generate_subtasks_with_docker_includes_terminal_and_file` (linhas 104-143)

Mesma logica com Docker mock — verifica presenca de terminal e file.

### `test_generate_subtasks_raises_when_no_barrier` (linhas 146-165)

Duplica o teste de barrier missing da camada agent, garantindo cobertura unitaria tambem.

### `test_generate_subtasks_model_resolution_param_over_env_and_default` (linhas 168-203)

Testa a cascata de resolucao de modelo com 3 chamadas consecutivas:

```python
monkeypatch.setenv("GENERATOR_MODEL", "env-model")
await generate_subtasks("scan", backend_profile, "/skills", model="param-model")  # → "param-model"
await generate_subtasks("scan", backend_profile, "/skills")                        # → "env-model"
monkeypatch.delenv("GENERATOR_MODEL")
await generate_subtasks("scan", backend_profile, "/skills")                        # → "claude-sonnet-4-20250514"

assert captured_models == ["param-model", "env-model", "claude-sonnet-4-20250514"]
```

| Chamada | Parametro `model` | Env `GENERATOR_MODEL` | Resultado esperado |
|---|---|---|---|
| 1 | `"param-model"` | `"env-model"` | `"param-model"` (parametro vence) |
| 2 | `None` | `"env-model"` | `"env-model"` (env var) |
| 3 | `None` | removida | `"claude-sonnet-4-20250514"` (default) |

### `test_generate_subtasks_raises_for_invalid_subtask_count` (linhas 206-233)

Forca o LLM a retornar 16 subtasks (`range(1, 17)`) — excede o limite de 15. Verifica que `GeneratorError` e levantada:

```python
with pytest.raises(GeneratorError, match="Generator failed to produce a plan"):
    await generate_subtasks("scan", backend_profile, "/skills")
```

---

## Testes — `tests/e2e/test_generator_claude_e2e.py` (camada E2E)

Teste end-to-end com o Claude real. Marcado com `@pytest.mark.e2e` — executado apenas via `workflow_dispatch`.

### `_load_anthropic_key_from_dotenv` (linhas 22-45)

```python
def _load_anthropic_key_from_dotenv() -> None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dotenv_path = os.path.join(repo_root, ".env")
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key != "ANTHROPIC_API_KEY":
                continue
            os.environ[key] = value.strip().strip('"').strip("'")
            return
```

Carrega `ANTHROPIC_API_KEY` do ficheiro `.env` na raiz do repositorio. Manuseia:
- Linhas de comentario (`#`)
- Linhas com prefixo `export `
- Valores entre aspas (`"key"` ou `'key'`)
- Ignora variaveis que nao sejam `ANTHROPIC_API_KEY`

### `skills_dir` fixture (linhas 48-61)

Cria um directorio temporario com duas FASE skills (`fase-1` e `fase-3`), cada uma com um `SKILL.md` minimalista. O formato segue o esperado pelo `load_fase_index` (frontmatter com `description`).

### `test_generate_subtasks_with_real_claude` (linhas 64-90)

```python
async def test_generate_subtasks_with_real_claude(skills_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _load_anthropic_key_from_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is required for real Claude E2E test")

    monkeypatch.delenv("GENERATOR_MODEL", raising=False)

    profile = BackendProfile(
        primary_target="https://example.com",
        backend_type="supabase",
        confidence="high",
        scan_path=["fase-1", "fase-3"],
        configs={"url": "https://example.supabase.co", "anon_key": "public-anon-key-placeholder"},
        subdomains=[],
    )

    subtasks = await generate_subtasks("scan https://example.com", profile, skills_dir)

    assert 1 <= len(subtasks) <= 15
    assert all(item.title for item in subtasks)
    assert all(item.description for item in subtasks)
    assert any(item.fase for item in subtasks)
```

O teste:
1. Carrega a API key do `.env` (ou skip se nao existir)
2. Remove `GENERATOR_MODEL` do ambiente para usar o default
3. Cria um `BackendProfile` Supabase com configs realistas
4. Chama `generate_subtasks` com o Claude real
5. Valida o contrato de output (1-15 subtasks, titulos/descricoes nao vazios, pelo menos uma com fase)

---

## Exemplo Completo

Fluxo de execucao do Generator de ponta a ponta:

```
1. Controller chama generate_subtasks()
   → input: "scan https://abc.supabase.co"
   → backend_profile: BackendProfile(backend_type="supabase", scan_path=["fase-1", "fase-3"])
   → skills_dir: "/workspace/skills"
   → docker_client: DockerClient (ou None)

2. load_fase_index(scan_path=["fase-1", "fase-3"], skills_dir)
   → retorna string com frontmatter + conteudo de SKILL.md de cada fase

3. render_generator_prompt(input, backend_profile, fase_index, "")
   → system_prompt: Jinja2 com instrucoes do Generator + FASE index injectado
   → user_prompt: Jinja2 com "scan https://abc.supabase.co"

4. Montar tools:
   → com Docker: [terminal, file, browser, memorist_stub, searcher_stub, subtask_list]
   → sem Docker:  [browser, memorist_stub, searcher_stub, subtask_list]

5. create_agent_graph(ChatAnthropic("claude-sonnet-4-20250514"), tools, barrier_names={"subtask_list"}, max_iterations=20)
   → retorna StateGraph compilado com recursion_limit=20

6. graph.ainvoke({"messages": [SystemMessage, HumanMessage]})
   → LLM chama tools (browser, etc.) para investigar o alvo
   → LLM eventualmente chama subtask_list([...]) → barrier_hit=True

7. Validar resultado:
   → barrier_hit == True ✓
   → barrier_result["subtasks"] e list com 1-15 items ✓
   → SubtaskInfo.model_validate(item) passa para cada item ✓

8. return list[SubtaskInfo]
   → Ex: [SubtaskInfo(title="Recon", description="Run nmap...", fase="fase-1"), ...]
```

---

## Padrao de Implementacao

O Generator estabelece o padrao para todos os agentes futuros:

```
async def run_<agent>(
    input: str,
    config: <AgentConfig>,
    skills_dir: str,
    docker_client: DockerClient | None = None,
    model: str | None = None,
) -> <ResultType>:
    1. Carregar skills relevantes via load_fase_index()
    2. Renderizar prompts via render_<agent>_prompt()
    3. Montar tools (conditional on docker_client)
    4. Criar ChatAnthropic com modelo resolvido (param → env → default)
    5. Criar graph via create_agent_graph() com barrier_names especifico
    6. Invocar graph com ainvoke()
    7. Validar barrier_result e extrair output
    8. Log + return resultado
```

Cada agente novo deve seguir este template, mudando:
- A funcao de renderizacao de prompt
- O conjunto de tools
- O `barrier_names` (cada agente tem o seu barrier de sinalizacao)
- A validacao do `barrier_result`

---

## Questoes Frequentes

### P: Porque e que o Generator usa `max_iterations=20` e nao o default de 100 do `create_agent_graph`?

A: O Generator tem uma tarefa bem definida (produzir um plano) e nao deve iterar indefinidamente. Se apos 20 chamadas ao LLM ele ainda nao chamou `subtask_list`, algo esta errado (prompt confuso, alvo ambiguo, LLM a divagar). O Adviser (US-008) intervem quando agentes fazem 20+ chamadas — aqui o proprio graph para antes disso.

### P: Porque e que `subtask_list` e tratado como barrier e nao como tool normal?

A: A tool `subtask_list` sinaliza **fim do planeamento**. Se fosse tool normal, o graph continuaria o loop e o LLM poderia chamar `subtask_list` multiplos vezes. O barrier pattern captura os args e termina o graph imediatamente — o resultado fica disponivel em `barrier_result` para extraccao.

### P: O que acontece se o LLM retornar 0 subtasks ou 20 subtasks?

A: Ambas as situacoes levantam `GeneratorError`. Zero subtasks significa que o Generator nao conseguiu produzir um plano (alvo invalido, LLM falhou). Mais de 15 viola o contract do PentAGI e pode indicar que o LLM nao entendeu as instrucoes. O controller deve capturar `GeneratorError` e tratar como falha de scan.

### P: Porque e que o campo `fase` em `SubtaskInfo` e opcional (`str | None`)?

A: Nem todas as subtasks pertencem a uma FASE especifica. Por exemplo, uma subtask de "analisar resultados" ou "preparar relatorio" pode nao estar ligada a uma FASE do scan. O campo e preenchido quando a subtask corresponde a uma FASE, mas nao e obrigatorio.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/agents/generator.py` | Implementacao principal do Generator agent — `generate_subtasks()`, `GeneratorError`, `_resolve_generator_model()` |
| `src/pentest/agents/__init__.py` | Exportacao publica de `GeneratorError` e `generate_subtasks` |
| `tests/agent/test_generator_agent.py` | Testes de camada Agent — happy path com plano realista, seleccao de tools, erro de barrier |
| `tests/unit/agents/test_generator.py` | Testes unitarios — validacao de output, conditional de Docker, cascata de modelo, contagem invalida |
| `tests/e2e/test_generator_claude_e2e.py` | Teste E2E com Claude real — carrega API key do `.env`, cria skills temporarias, valida contrato |

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-037-BASE-GRAPH-EXPLAINED]] — LangGraph StateGraph, BarrierAwareToolNode
- [[US-038-BARRIERS-EXPLAINED]] — Barrier tool pattern, `subtask_list` tool
- [[US-039-TERMINAL-FILE-EXPLAINED]] — Terminal e file tools (Docker execution)
- [[US-040-BROWSER-TOOL-EXPLAINED]] — Browser tool (HTTP content fetching)
- [[US-041-STUBS-EXPLAINED]] — Memorist e searcher stub tools
- [[US-042-SKILL-LOADER-EXPLAINED]] — FASE skill index loader
- [[US-043-GENERATOR-PROMPTS-EXPLAINED]] — Jinja2 prompt renderer
- [[AGENT-ARCHITECTURE]] — Papel do Generator no sistema de 12 agentes
- [[EXECUTION-FLOW]] — Ciclo de vida do scan (7 fases)
