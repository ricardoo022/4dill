---
tags: [agents]
---

# US-037: Agent State e Base Graph — Explicacao Detalhada

Este documento explica linha a linha o ficheiro `src/pentest/agents/base.py`, o padrao base reutilizavel por todos os 12 agentes do sistema.

---

## Contexto

Todos os agentes no PentAGI usam o mesmo loop: chamar LLM → executar tool calls → verificar barriers → repetir. Em LangGraph, isto e um `StateGraph` com 2 nodes (`call_llm` + `BarrierAwareToolNode`) e routing condicional. Implementamos uma vez e todos os agentes reutilizam mudando apenas: tools, barrier_names, system prompt, e max_iterations.

---

## Imports (linhas 1-7)

```python
from typing import Annotated, Any
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict
```

| Import | Para que serve |
|---|---|
| `BaseChatModel` | Interface base de qualquer LLM (Claude, GPT, etc.) — aceitar qualquer provider |
| `AIMessage` | Mensagem gerada pelo LLM (pode ter `content` texto ou `tool_calls`) |
| `BaseMessage` | Tipo base de todas as mensagens (System, Human, AI, Tool) |
| `StateGraph` | Classe principal do LangGraph para construir grafos com estado |
| `START, END` | Nodes especiais que marcam entrada e saida do grafo |
| `add_messages` | Reducer que faz append inteligente de mensagens (deduplica por ID) |
| `ToolNode` | Node prebuilt do LangGraph que executa tool calls e devolve ToolMessages |
| `TypedDict` | Para definir o schema do state com tipos |
| `Annotated` | Para associar reducers aos campos do state |

---

## AgentState (linhas 10-13)

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    barrier_result: dict[str, Any] | None
    barrier_hit: bool
```

E a memoria partilhada do grafo. Todos os nodes leem e escrevem neste state.

### Campo `messages`

```python
messages: Annotated[list[BaseMessage], add_messages]
```

A lista completa de mensagens da conversa. O `Annotated[..., add_messages]` define o **reducer** — quando um node retorna `{"messages": [nova_msg]}`, o LangGraph nao substitui a lista, faz **append**. Sem reducer, perderias o historico todo a cada update.

Exemplo do conteudo durante uma execucao:

```python
[
    SystemMessage("Tu es o Generator. Cria um plano de pentest..."),
    HumanMessage("Target: 10.0.0.1, scope: web app"),
    AIMessage(tool_calls=[{"name": "terminal", "args": {"command": "nmap 10.0.0.1"}}]),
    ToolMessage(content="PORT 22/tcp open ssh\n80/tcp open http", tool_call_id="call_1"),
    AIMessage(tool_calls=[{"name": "subtask_list", "args": {"subtasks": [...]}}]),
    ToolMessage(content="barrier processed", tool_call_id="call_2"),
]
```

### Campo `barrier_result`

```python
barrier_result: dict[str, Any] | None
```

Quando o LLM chama a barrier tool (ex: `subtask_list`), os **argumentos** dessa tool call ficam aqui. E o resultado real do agente — nao o return value da tool (que e so uma string de confirmacao), mas os args que o LLM passou.

Exemplo: `{"subtasks": ["Scan ports", "Check CVEs", "Test SQLi"], "message": "Plan ready"}`

E `None` enquanto o agente ainda nao terminou.

### Campo `barrier_hit`

```python
barrier_hit: bool
```

Flag simples: o agente ja chamou a barrier tool? Usada pelo routing para decidir se termina o grafo ou volta ao LLM.

---

## BarrierAwareToolNode (linhas 16-41)

```python
class BarrierAwareToolNode:
    def __init__(self, tools: list[Any], barrier_names: set[str] | list[str]):
        self.tool_node = ToolNode(tools, handle_tool_errors=True)
        self.barrier_names = set(barrier_names)
```

### O que e

Wrapper a volta do `ToolNode` standard do LangGraph. Adiciona uma unica funcionalidade: **detecao de barrier**. Depois de executar todas as tool calls, verifica se alguma era barrier e, se sim, extrai os argumentos.

### `__init__`

- `ToolNode(tools, handle_tool_errors=True)` — cria o executor de tools. O `handle_tool_errors=True` significa: se uma tool crashar (raise exception), em vez de rebentar o programa, devolve o erro como `ToolMessage` para o LLM poder tentar outra coisa.
- `set(barrier_names)` — converte para set para lookup O(1). Exemplo: `{"subtask_list"}` para o Generator.

### `__call__` — o metodo principal

```python
def __call__(self, state: AgentState) -> dict[str, Any]:
```

E chamado pelo LangGraph **uma vez por turno** (nao por tool individual). Quando o LLM responde com tool calls, o grafo chama este metodo.

#### Passo 1: Executar TODAS as tool calls (linha 23)

```python
result = self.tool_node.invoke(state)
```

O `ToolNode` pega na ultima `AIMessage` do state (que contem os `tool_calls`), executa **cada uma**, e devolve as `ToolMessage`s com os resultados. Se o LLM pediu `[terminal("nmap ..."), search("CVE ...")]`, ambas sao executadas aqui.

O `result` e um dict: `{"messages": [ToolMessage(...), ToolMessage(...)]}`.

#### Passo 2: Verificar se alguma tool call era barrier (linhas 27-34)

```python
last_ai_msg = state["messages"][-1]
barrier_result = None

if isinstance(last_ai_msg, AIMessage) and hasattr(last_ai_msg, "tool_calls"):
    for tc in last_ai_msg.tool_calls:
        if tc["name"] in self.barrier_names:
            barrier_result = tc["args"]
            break
```

- `state["messages"][-1]` — a ultima mensagem no state **antes** das tools executarem. E a `AIMessage` do LLM que contem os `tool_calls`.
- Percorre cada tool call e verifica se o nome esta em `barrier_names`.
- Se encontra: guarda os `args` (ex: `{"subtasks": [...]}`) — **nao** o return value da tool.
- `break` — para no primeiro barrier encontrado.

Porque os `args` e nao o return? Porque a barrier tool em si so valida e retorna uma string generica tipo `"ok"`. Os dados reais (a lista de subtasks, o report, etc.) estao nos argumentos que o LLM passou ao chamar a tool.

Cada `tc` (tool call) tem esta estrutura:

```python
{
    "name": "subtask_list",                              # qual tool
    "args": {"subtasks": ["Scan ports", "Test SQLi"]},   # argumentos (O QUE QUEREMOS)
    "id": "call_abc123",                                 # ID unico
    "type": "tool_call",
}
```

#### Passo 3: Retornar o state update (linhas 37-41)

```python
return {
    "messages": result.get("messages", []),
    "barrier_hit": barrier_result is not None,
    "barrier_result": barrier_result,
}
```

- `messages` — as `ToolMessage`s resultantes (vao ser adicionadas ao historico pelo reducer `add_messages`)
- `barrier_hit` — `True` se encontrou barrier, `False` caso contrario
- `barrier_result` — os args da barrier tool, ou `None`

O LangGraph aplica este dict ao state: faz append das messages e sobrescreve `barrier_hit` e `barrier_result`.

---

## create_agent_graph (linhas 44-78)

```python
def create_agent_graph(
    llm: BaseChatModel,
    tools: list[Any],
    barrier_names: set[str] | list[str],
    max_iterations: int = 100,
):
```

Factory que recebe as pecas e devolve um grafo compilado pronto a executar.

### Parametros

| Parametro | O que e | Exemplo |
|---|---|---|
| `llm` | Qualquer LLM via interface LangChain | `ChatAnthropic(model="claude-sonnet-4-5")` |
| `tools` | Lista de ferramentas disponiveis | `[terminal, search, subtask_list]` |
| `barrier_names` | Tools que sinalizam "terminei" | `{"subtask_list"}` |
| `max_iterations` | Limite de iteracoes do loop | `20` para Generator, `100` para outros |

### Linha 50: Preparar o LLM

```python
llm_with_tools = llm.bind_tools(tools)
```

Diz ao LLM quais ferramentas existem. Por baixo, quando chamas `.invoke()`, o pedido HTTP a API inclui a definicao de cada tool (nome, descricao, schema dos parametros). O LLM nao "lembra" das tools entre chamadas — sao enviadas **sempre** em cada request.

Exemplo do que vai para a API:

```json
{
  "model": "claude-sonnet-4-5-20250514",
  "messages": [...],
  "tools": [
    {
      "name": "terminal",
      "description": "Run a command in the Kali Linux container.",
      "input_schema": {
        "type": "object",
        "properties": {
          "command": {"type": "string"}
        }
      }
    }
  ]
}
```

As definicoes vem do decorator `@tool` de cada ferramenta:
- `name` ← nome da funcao
- `description` ← docstring
- `input_schema` ← type hints dos parametros

### Linha 51: Criar o node de tools

```python
barrier_node = BarrierAwareToolNode(tools, barrier_names)
```

Cria o executor de tools com detecao de barrier (explicado acima).

### Linhas 53-55: Node `call_llm`

```python
def call_llm(state: AgentState) -> dict[str, Any]:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}
```

1. Pega em **todas** as messages do state (system prompt + historico completo)
2. Envia ao LLM via `.invoke()` — chamada sincrona e bloqueante (espera pela resposta da API)
3. O LLM devolve uma `AIMessage` que pode ser:
   - **Texto**: `AIMessage(content="Aqui esta o plano...")` — sem tool calls
   - **Tool calls**: `AIMessage(tool_calls=[{"name": "terminal", "args": {...}}])` — quer usar ferramentas
4. Retorna `{"messages": [response]}` — o reducer `add_messages` adiciona a resposta ao historico

### Linhas 57-61: Routing apos o LLM

```python
def route_after_llm(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "execute_tools"
    return END
```

Olha para a ultima mensagem (a resposta do LLM). Decisao binaria:
- Tem `tool_calls` → vai para `execute_tools` (o BarrierAwareToolNode)
- Nao tem (texto puro) → vai para `END` (o agente respondeu sem usar tools, grafo termina)

### Linhas 63-66: Routing apos as tools

```python
def route_after_tools(state: AgentState) -> str:
    if state.get("barrier_hit"):
        return END
    return "call_llm"
```

Depois do `BarrierAwareToolNode` executar:
- `barrier_hit == True` → `END` (o agente terminou, resultado em `barrier_result`)
- `barrier_hit == False` → volta para `call_llm` (o LLM ve os resultados das tools e decide o proximo passo)

O `state.get("barrier_hit")` (em vez de `state["barrier_hit"]`) e defensivo — se o campo nao existir no state, retorna `None` (falsy) em vez de crashar.

### Linhas 68-78: Montar e compilar o grafo

```python
workflow = StateGraph(AgentState)

workflow.add_node("call_llm", call_llm)
workflow.add_node("execute_tools", barrier_node)

workflow.add_edge(START, "call_llm")
workflow.add_conditional_edges("call_llm", route_after_llm, ["execute_tools", END])
workflow.add_conditional_edges("execute_tools", route_after_tools, ["call_llm", END])

return workflow.compile()
```

Passo a passo:

1. `StateGraph(AgentState)` — cria um grafo vazio com `AgentState` como memoria partilhada
2. `add_node` — regista os 2 nodes:
   - `"call_llm"` → a funcao que chama o LLM
   - `"execute_tools"` → o `BarrierAwareToolNode`
3. `add_edge(START, "call_llm")` — edge fixa: quando o grafo arranca vai **sempre** para `call_llm`
4. `add_conditional_edges("call_llm", route_after_llm, ["execute_tools", END])` — depois de `call_llm`, chama a funcao `route_after_llm` que devolve o nome do proximo node. O terceiro argumento declara os destinos possiveis (para validacao pelo LangGraph)
5. `add_conditional_edges("execute_tools", route_after_tools, ["call_llm", END])` — idem para apos as tools
6. `compile()` — valida o grafo (nodes existem, edges fazem sentido) e devolve um `CompiledGraph` executavel

### Diagrama do grafo resultante

```
    ┌─────────────────────────────────────────┐
    │                                         │
    v                                         │
  START                                       │
    │                                         │
    v                                         │
┌────────┐    tool calls?     ┌─────────────┐ │
│call_llm│───── SIM ─────────>│execute_tools│ │
└────────┘                    └─────────────┘ │
    │                               │         │
    │ NAO (texto)          barrier? │         │
    │                        /      \         │
    v                      SIM      NAO ──────┘
   END                      │
                            v
                           END
```

Sao so **2 nodes** e **3 edges** — mas criam um loop que pode correr dezenas de vezes. Cada volta: LLM pensa → executa tools → verifica barrier → repete.

---

## Como cada agente reutiliza o padrao

```python
# Generator — para quando chama subtask_list
generator = create_agent_graph(
    llm=ChatAnthropic(model="claude-sonnet-4-5"),
    tools=[terminal, search, subtask_list],
    barrier_names={"subtask_list"},
    max_iterations=20,
)

# Scanner — para quando chama scan_complete
scanner = create_agent_graph(
    llm=ChatAnthropic(model="claude-sonnet-4-5"),
    tools=[terminal, browser, scan_complete],
    barrier_names={"scan_complete"},
    max_iterations=100,
)

# Invocacao
result = generator.invoke({"messages": [system_prompt, human_msg]})
plan = result["barrier_result"]  # {"subtasks": ["Scan ports", "Test SQLi"]}
```

O que muda por agente:

| Agente | Tools | Barrier | max_iterations |
|---|---|---|---|
| Generator | terminal, search, subtask_list | `subtask_list` | 20 |
| Orchestrator | ask_scanner, ask_coder, ask_searcher, done | `done` | 100 |
| Scanner | terminal, browser, scan_complete | `scan_complete` | 100 |
| Coder | terminal, write_file, code_ready | `code_ready` | 100 |
| Searcher | web_search, search_done | `search_done` | 100 |
| Memorist | vector_store, memory_done | `memory_done` | 20 |
| Reporter | report_ready | `report_ready` | 20 |
| Refiner | adjust_plan, refine_done | `refine_done` | 20 |
| Adviser | advise | `advise` | 20 |
| Reflector | reflect | `reflect` | 5 |

---

## Exemplo completo: 3 turnos do Generator

```
Turno 1:
  call_llm → LLM: "Preciso de mais info. Vou fazer um scan."
             tool_calls: [terminal(command="nmap 10.0.0.1")]
  route_after_llm → tem tool_calls → "execute_tools"
  execute_tools → ToolNode executa nmap → ToolMessage("PORT 22 open, PORT 80 open")
                  Barrier check: "terminal" in {"subtask_list"}? NAO
  route_after_tools → barrier_hit=False → "call_llm"

Turno 2:
  call_llm → LLM ve resultado do nmap, quer pesquisar CVEs
             tool_calls: [search(query="CVE nginx 1.18")]
  route_after_llm → tem tool_calls → "execute_tools"
  execute_tools → ToolNode executa search → ToolMessage("CVE-2021-23017: buffer overflow...")
                  Barrier check: "search" in {"subtask_list"}? NAO
  route_after_tools → barrier_hit=False → "call_llm"

Turno 3:
  call_llm → LLM: "Ja tenho informacao suficiente, aqui esta o plano"
             tool_calls: [subtask_list(subtasks=["Scan ports", "Check CVEs", "Test SQLi"])]
  route_after_llm → tem tool_calls → "execute_tools"
  execute_tools → ToolNode executa subtask_list → ToolMessage("ok")
                  Barrier check: "subtask_list" in {"subtask_list"}? SIM
                  barrier_result = {"subtasks": ["Scan ports", "Check CVEs", "Test SQLi"]}
  route_after_tools → barrier_hit=True → END

State final:
  barrier_result = {"subtasks": ["Scan ports", "Check CVEs", "Test SQLi"]}
```

O controller extrai `result["barrier_result"]` e cria as subtasks na base de dados.

---

## Bug identificado na review do PR #3

### `recursion_limit` nao e aplicado

```python
def create_agent_graph(llm, tools, barrier_names, max_iterations: int = 100):
    ...
    return workflow.compile()  # max_iterations NAO e usado!
```

O parametro `max_iterations` e recebido mas nunca passado ao `compile()`. Deveria ser:

```python
return workflow.compile(recursion_limit=max_iterations)
```

Sem isto, nao ha protecao contra loops infinitos alem do default interno do LangGraph (25 iteracoes). O `recursion_limit` e o equivalente ao `maxLimitedAgentChainIterations = 20` do PentAGI — e a principal safety net do sistema.

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[US-038-BARRIERS-EXPLAINED]]
- [[US-039-TERMINAL-FILE-EXPLAINED]]
