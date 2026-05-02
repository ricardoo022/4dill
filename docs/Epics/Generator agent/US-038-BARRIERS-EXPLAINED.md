---
tags: [agents]
---

# US-038: Barrier Tools — Explicacao Detalhada

Este documento explica o padrão de **Barrier Tools** e como se integram com o `BarrierAwareToolNode` descrito em US-037. Barrier tools são sinais de terminação que permitem ao agente comunicar o resultado final ao sistema.

---

## Contexto: O que sao Barrier Tools?

Em US-037, aprendemos que o `BarrierAwareToolNode` verifica se o LLM chamou uma ferramenta cujo nome está em `barrier_names`. Se sim, extrai os argumentos dessa tool call e marca `barrier_hit = True`, terminando o agente.

As **barrier tools** são as ferramentas designadas com este propósito. Nao sao diferentes de ferramentas normais no ponto de vista do LLM — o LLM chama-as como qualquer outra tool. A diferenca é **semantica**: quando o LLM chama a barrier tool, o agente termina e passa o resultado para o controller.

---

## Arquitetura: Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Loop                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. LLM gera resposta com tool calls                       │
│     AIMessage(tool_calls=[{"name": "subtask_list",         │
│                            "args": {...dados reais...}}])  │
│                                                             │
│  2. BarrierAwareToolNode executa as tools                  │
│                                                             │
│  3. Verifica: "subtask_list" in barrier_names?             │
│                                                             │
│  4. SIM → extrai args e marca barrier_hit=True             │
│     state["barrier_result"] = args                         │
│     state["barrier_hit"] = True                            │
│                                                             │
│  5. Routing após tools: barrier_hit=True → END             │
│                                                             │
│  6. Agent termina                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ Controller                                                   │
├──────────────────────────────────────────────────────────────┤
│ result = agent.invoke(...)                                   │
│ dados = result["barrier_result"]  # Extrai os dados reais   │
│ Processa dados (cria records, atualiza BD, etc.)            │
└──────────────────────────────────────────────────────────────┘
```

**Ponto critico**: Os dados reais nao estao no return value da tool (que e apenas confirmacao), mas nos **argumentos** (`args`) da tool call.

---

## Modelos: tool_args.py

Nao temos modelos barrier-especificos em `tool_args.py`. As barrier tools usam modelos definidos em otros ficheiros (ex: `SubtaskList` em `src/pentest/models/subtask.py`).

Entretanto, `tool_args.py` contem schemas para tools normais que coexistem com barriers:

| Tool | Modelo | Campo chave |
|------|--------|-------------|
| `terminal` | `TerminalAction` | `input: str` (comando) |
| `file` | `FileAction` | `action: Literal["read_file", "update_file"]` |
| `browser` | `BrowserAction` | `url: str` |

As ferramentas normais sao executadas mas **nao** sao barriers — nao terminam o agente.

---

## Barrier Tools Atuais

### 1. `subtask_list` (Generator Barrier)

**Ficheiro**: `src/pentest/tools/barriers.py`

```python
@tool(args_schema=SubtaskList)
def subtask_list(subtasks: list, message: str) -> str:
    """
    Submit the final generated subtask list to the user.
    Use this tool ONLY when you have finished planning.
    """
    return f"subtask list successfully processed with {len(subtasks)} subtasks"
```

#### Proposito

Sinalizacao de terminacao para o **Generator Agent**. Quando o LLM chama `subtask_list`, significa: "Ja analisei o target e criei o plano. Aqui estao as subtasks."

#### Schema (SubtaskList)

Definido em `src/pentest/models/subtask.py`:

```python
class SubtaskInfo(BaseModel):
    title: str                          # Ex: "Scan ports"
    description: str                    # Ex: "Enumerar portas abertas com nmap"
    fase: str | None = None             # Ex: "reconnaissance", opcional

class SubtaskList(BaseModel):
    subtasks: list[SubtaskInfo]         # Min 1, max 15 subtasks
    message: str                        # Mensagem contextual
```

#### Validacao

- `title` e `description` sao obrigatorios e nao podem ser brancos
- Lista deve ter entre 1 e 15 subtasks
- Campo `fase` e opcional

#### Return Value vs Arguments

```python
# O que o LLM chama:
{
    "tool_calls": [{
        "name": "subtask_list",
        "args": {
            "subtasks": [
                {"title": "Scan ports", "description": "nmap -A target", "fase": "recon"},
                {"title": "Check CVEs", "description": "nuclei -t cves"}
            ],
            "message": "Initial plan ready"
        }
    }]
}

# O que a tool retorna:
"subtask list successfully processed with 2 subtasks"

# O que BarrierAwareToolNode extrai:
state["barrier_result"] = {
    "subtasks": [...],          # OS DADOS REAIS
    "message": "Initial plan ready"
}
```

**Porque e assim?** Porque a tool nao faz nada com os dados — apenas valida (pelo schema Pydantic) e confirma. Os dados reais viajam via `args`. O return value e apenas confirmacao sintaxe para o LLM ("tudo ok, tool executou").

#### Fluxo no Agent

```
1. LLM analisa target, coleta info via terminal/search/browser
2. LLM: "Ja tenho informacao suficiente"
3. LLM chama subtask_list com a lista de subtasks
4. BarrierAwareToolNode:
   a. ToolNode executa subtask_list → retorna ToolMessage("subtask list successfully...")
   b. Verifica: "subtask_list" in {"subtask_list"}? SIM
   c. Extrai args → state["barrier_result"] = {subtasks: [...]}
   d. Marca barrier_hit = True
5. Routing: barrier_hit=True → END
6. Agent termina
7. Controller lê result["barrier_result"] e cria tasks na BD
```

---

## Padrão de Implementação de Barrier Tools

Qualquer barrier tool segue este padrão:

### Template

```python
from langchain_core.tools import tool
from pentest.models.xxx import YourSchema  # Schema com os dados reais

@tool(args_schema=YourSchema)
def your_barrier(field1: str, field2: list, ... , message: str) -> str:
    """
    Human-friendly description of what this barrier signals.

    This is the termination signal for the [AgentName] Agent.
    """
    # Validacao adicional (opcional — o Pydantic schema ja faz muita)
    # Neste caso, a tool nao faz processamento, apenas confirma

    # Retornar confirmacao generica
    return f"[Agent] barrier processed with {len(field2)} items"
```

### Regras Obrigatorias

1. **Nunca processam os dados** — apenas confirmam. Qualquer processamento deve estar no controller.
2. **Docstring clara** — para o LLM entender quando usa-la.
3. **Return value simples** — string generica de confirmacao.
4. **Args sao os dados reais** — schema Pydantic valida estrutura e conteudo.
5. **Nunca fazem side effects** — sem I/O, sem BD, sem ficheiros. Isso fica para o controller.
6. **Exception handling nao e necessario** — o `BarrierAwareToolNode` com `handle_tool_errors=True` trata crashes.

---

## Conexao com BarrierAwareToolNode (US-037)

### Como o BarrierAwareToolNode Identifica Barriers

Ficheiro: `src/pentest/agents/base.py`

```python
class BarrierAwareToolNode:
    def __init__(self, tools: list[Any], barrier_names: set[str] | list[str]):
        self.tool_node = ToolNode(tools, handle_tool_errors=True)
        self.barrier_names = set(barrier_names)  # Ex: {"subtask_list"}

    def __call__(self, state: AgentState) -> dict[str, Any]:
        # Passo 1: Executar todas as tool calls (normais e barriers)
        result = self.tool_node.invoke(state)

        # Passo 2: Verificar se alguma era barrier
        last_ai_msg = state["messages"][-1]  # AIMessage do LLM
        barrier_result = None

        if isinstance(last_ai_msg, AIMessage) and hasattr(last_ai_msg, "tool_calls"):
            for tc in last_ai_msg.tool_calls:
                if tc["name"] in self.barrier_names:  # "subtask_list" in {"subtask_list"}?
                    barrier_result = tc["args"]
                    break

        # Passo 3: Atualizar state
        return {
            "messages": result.get("messages", []),
            "barrier_hit": barrier_result is not None,
            "barrier_result": barrier_result,
        }
```

### Processo Linha a Linha

1. **`self.barrier_names = set(barrier_names)`**
   - Recebe lista ou set de nomes de tools barrier
   - Ex: `barrier_names={"subtask_list"}` para Generator
   - Set para lookup O(1): `"subtask_list" in self.barrier_names` e muito rapido

2. **`last_ai_msg = state["messages"][-1]`**
   - Ultima mensagem do state = ultima resposta do LLM
   - Contem os `tool_calls` que o LLM gerou

3. **Loop sobre tool calls**
   ```python
   for tc in last_ai_msg.tool_calls:
       if tc["name"] in self.barrier_names:
   ```
   - Cada `tc` (tool call) tem:
     ```python
     {
         "name": "subtask_list",              # <-- O QUE PROCURAMOS
         "args": {"subtasks": [...], ...},    # <-- OS DADOS
         "id": "call_abc123"
     }
     ```
   - Se `tc["name"]` esta em `barrier_names`, encontrou a barrier

4. **Extrair args**
   ```python
   barrier_result = tc["args"]
   ```
   - Nao e o return value da tool, mas os argumentos originais
   - Ex: `{"subtasks": ["Scan ports", "Check CVEs"], "message": "..."}`

5. **Marcar barrier_hit**
   ```python
   "barrier_hit": barrier_result is not None
   ```
   - `True` se encontrou barrier, `False` senao

---

## Por que os Arguments e nao o Return Value?

### Cenario 1: Usar return value

```python
@tool(args_schema=SubtaskList)
def subtask_list(subtasks: list, message: str) -> str:
    return str(subtasks)  # ERRADO: dados escondidos em string

# ToolMessage resultado
ToolMessage(content='[{"title": "Scan ports"}, ...]')

# Problema: Desserializar string e frágil (JSON em string)
```

### Cenario 2: Usar arguments (CORRETO)

```python
@tool(args_schema=SubtaskList)
def subtask_list(subtasks: list, message: str) -> str:
    return "ok"  # Apenas confirmacao

# tool_calls structure
{
    "name": "subtask_list",
    "args": {
        "subtasks": [{"title": "Scan ports"}, ...],  # Estrutura preservada
        "message": "Initial plan"
    },
    "id": "call_123"
}

# BarrierAwareToolNode extrai args directamente
barrier_result = tc["args"]  # Dict com estrutura original
```

### Vantagens

| Aspecto | Arguments | Return Value |
|--------|-----------|--------------|
| Tipo | Dict estruturado | String |
| Segurança | Validado por Pydantic | Nao validado |
| Parsing | Directo | Desserializacao fragil |
| Compatibilidade | LLM entende (schema obrigatorio) | LLM pode gerar qualquer coisa |
| Rastreabilidade | Registado no tool_calls | Inacessivel sem parsing |

---

## Exemplo Completo: Do LLM ao Controller

### Codigo do Generator

```python
from pentest.agents.base import create_agent_graph
from pentest.tools.terminal import create_terminal_tool
from pentest.tools.browser import create_browser_tool
from pentest.tools.barriers import subtask_list

# Criar grafo
generator = create_agent_graph(
    llm=ChatAnthropic(model="claude-sonnet-4-5"),
    tools=[
        create_terminal_tool(docker_client, container_id),
        create_browser_tool(),
        subtask_list,
    ],
    barrier_names={"subtask_list"},
    max_iterations=20,
)

# Invocar
system_prompt = SystemMessage("Tu es o Generator. Cria um plano de pentest...")
human_msg = HumanMessage("Target: 10.0.0.1, scope: web application")

result = generator.invoke({
    "messages": [system_prompt, human_msg]
})

# Extrair dados
plan = result["barrier_result"]  # Dict: {"subtasks": [...], "message": "..."}

# Controller processa
for subtask in plan["subtasks"]:
    db.create_task(
        title=subtask["title"],
        description=subtask["description"],
        phase=subtask["fase"]
    )
```

### Passo a Passo Interno

```
[Turno 1]
LLM: "Vou fazer reconnaissance"
Tool calls: [terminal(input="nmap 10.0.0.1")]

BarrierAwareToolNode.__call__:
  - Executa terminal → ToolMessage("PORT 22 open...")
  - Verifica: "terminal" in {"subtask_list"}? NAO
  - barrier_hit = False

Routing: barrier_hit=False → volta a call_llm

[Turno 2]
LLM: "Vou verificar vulnerabilidades conhecidas"
Tool calls: [browser(url="https://cve.mitre.org", action="links")]

BarrierAwareToolNode.__call__:
  - Executa browser → ToolMessage("https://...")
  - Verifica: "browser" in {"subtask_list"}? NAO
  - barrier_hit = False

Routing: barrier_hit=False → volta a call_llm

[Turno 3]
LLM: "Tenho informacao suficiente. Aqui esta o plano"
Tool calls: [subtask_list(
    subtasks=[
        SubtaskInfo(title="Scan ports", description="nmap -A", fase="recon"),
        SubtaskInfo(title="Check CVEs", description="nuclei", fase="research")
    ],
    message="Initial plan"
)]

BarrierAwareToolNode.__call__:
  - Executa subtask_list → ToolMessage("subtask list successfully processed...")
  - Verifica: "subtask_list" in {"subtask_list"}? SIM ✓
  - barrier_result = {
        "subtasks": [
            {"title": "Scan ports", ...},
            {"title": "Check CVEs", ...}
        ],
        "message": "Initial plan"
    }
  - barrier_hit = True

Routing: barrier_hit=True → END

[Agent Termina]
result["barrier_result"] = {
    "subtasks": [...],
    "message": "Initial plan"
}

[Controller]
Lê barrier_result e cria tasks na BD
```

---

## Extensibilidade: Adicionar Novas Barriers

### Passo 1: Definir o Schema

```python
# src/pentest/models/my_barrier.py
from pydantic import BaseModel, Field

class MyBarrierData(BaseModel):
    result: str = Field(..., description="O resultado")
    metadata: dict = Field(default_factory=dict)
```

### Passo 2: Implementar a Barrier Tool

```python
# src/pentest/tools/my_tool.py
from langchain_core.tools import tool
from pentest.models.my_barrier import MyBarrierData

@tool(args_schema=MyBarrierData)
def my_barrier(result: str, metadata: dict, message: str = "") -> str:
    """
    Sinalizacao de terminacao para MyAgent.
    Use esta tool quando terminou o seu trabalho.
    """
    return f"MyAgent barrier processed: {result}"
```

### Passo 3: Usar no Agent

```python
from pentest.agents.base import create_agent_graph
from pentest.tools.my_tool import my_barrier

agent = create_agent_graph(
    llm=...,
    tools=[other_tools, my_barrier],
    barrier_names={"my_barrier"},  # <-- Registar o nome
    max_iterations=50,
)

result = agent.invoke({"messages": [...]})
data = result["barrier_result"]  # {"result": "...", "metadata": {...}}
```

Nada muda no `BarrierAwareToolNode` — funciona genericamente. So precisa registar o nome em `barrier_names`.

---

## Resumo: Arquitetura de Barriers

| Componente | Responsabilidade |
|---|---|
| **Barrier Tool** (`subtask_list`, etc.) | Validar schema, retornar confirmacao |
| **Schema (Pydantic)** | Definir e validar estrutura dos dados reais |
| **BarrierAwareToolNode** | Detectar que a tool e barrier, extrair args |
| **Agent State** | Guardar `barrier_result` e `barrier_hit` |
| **Controller** | Extrair `result["barrier_result"]` e processar |

---

## Questoes Frequentes

### P: Por que a barrier tool retorna "ok" em vez dos dados?

A: O LLM e o agent loop esperam que tools retornem strings (ToolMessage). Os dados estruturados (listas, dicts) nao cabem bem em ToolMessage.content. A Pydantic schema ja validou e estruturou os args, que ficam no tool_calls. O return value e apenas para o LLM saber que a tool executou.

### P: Pode haver multiplas barriers ativas ao mesmo tempo?

A: Sim, tecnicamente. Se `barrier_names={"subtask_list", "another_tool"}`, o BarrierAwareToolNode procura pela primeira que encontrar. Porem, a pratica e ter **uma** barrier por agente.

### P: O que acontece se a barrier tool nao valida (Pydantic error)?

A: O `ToolNode` com `handle_tool_errors=True` apanha a excecao e devolve um ToolMessage com o erro. O LLM ve o erro e pode tentar de novo com argumentos corretos.

### P: Pode invocar a barrier tool manualmente (nao via LLM)?

A: Sim. `subtask_list(subtasks=[...], message="...")` funciona. Mas o BarrierAwareToolNode so detecta barriers quando veem de `tool_calls` na AIMessage do LLM.

### P: Como garantir que o LLM nao esquece de chamar a barrier?

A: Pelo system prompt. Tipicamente: "Quando tiveres terminado, SEMPRE chama a tool `subtask_list` com os resultados finais."

---

## Related Notes

- [Docs Home](../../README.md)
- **US-037-BASE-GRAPH-EXPLAINED.md** — Explicacao do `StateGraph` e `BarrierAwareToolNode`
- **src/pentest/agents/base.py** — Implementacao do grafo base
- **src/pentest/tools/barriers.py** — Barrias tools atuais
- **src/pentest/models/subtask.py** — Schema `SubtaskList`
- **src/pentest/models/tool_args.py** — Schemas de outras tools
