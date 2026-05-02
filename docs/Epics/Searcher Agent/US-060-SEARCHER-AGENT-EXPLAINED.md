---
tags: [agent, searcher, delegation, langgraph]
---

# US-060: Searcher Agent Completo + Delegation Handler — Explicacao Detalhada

Esta funcionalidade implementa o Searcher Agent completo, um agente especializado em pesquisa na web e em bases de conhecimento internas, juntamente com uma tool de delegacao que permite a outros agentes (como o Generator) solicitar pesquisas complexas de forma assincrona.

Este documento explica as alteracoes em `src/pentest/agents/searcher.py`, `src/pentest/agents/base.py`, `src/pentest/agents/generator.py` e `src/pentest/agents/__init__.py`.

## Contexto

O Searcher Agent e o componente do LusitAI responsavel por expandir o conhecimento do sistema atraves de fontes externas e internas. Ele une os modelos de dados de pesquisa, os barramentos (barriers) de finalizacao, os motores de busca (DuckDuckGo, Tavily) e o acesso ao vector database. A delegacao permite que agentes de alto nivel nao fiquem sobrecarregados com a logica de pesquisa, tratando-a como uma chamada de ferramenta externa que retorna um relatorio consolidado.

---

## Base Graph: Retry Policy (`src/pentest/agents/base.py`)

Foi adicionada uma politica de retry global no padrao base de grafos de agentes para proteger contra falhas transientes de APIs de LLM.

```python
from langgraph.types import RetryPolicy

# ...

def create_agent_graph(
    llm: BaseChatModel,
    tools: list[Any],
    barrier_names: set[str] | list[str],
    max_iterations: int = 100,
):
    # ...
    workflow = StateGraph(AgentState)

    workflow.add_node(
        "call_llm",
        call_llm,
        retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0),
    )
    # ...
```

| Parametro | Tipo | Valor | Explicacao |
|---|---|---|---|
| `max_attempts` | `int` | `3` | Numero maximo de tentativas em caso de erro transiente. |
| `initial_interval` | `float` | `1.0` | Intervalo inicial em segundos entre tentativas. |

---

## Searcher Agent (`src/pentest/agents/searcher.py`)

Este novo ficheiro contem a logica central do agente e a factory para a sua tool de delegacao.

### `perform_search`

Funcao assincrona que orquestra a execucao do grafo do Searcher.

```python
async def perform_search(
    question: str,
    llm: BaseChatModel,
    db_session: AsyncSession | None = None,
    execution_context: str = "",
    task: str | None = None,
    subtask: str | None = None,
) -> str:
    # ... montagem de tools ...
    # ... renderizacao de prompt ...
    # ... execucao do grafo ...
```

**Fluxo de Execucao:**
1. **Deteccao de Ferramentas:** Verifica a disponibilidade de DuckDuckGo e Tavily. Se nenhum estiver disponivel, interrompe precocemente.
2. **Montagem do Inventario:** Adiciona `browser`, `search_answer` (se DB disponivel), `memorist` (stub) e a barrier `search_result`.
3. **Renderizacao:** Utiliza `render_searcher_prompt` para gerar os prompts de sistema e utilizador com base no contexto.
4. **Execucao:** Cria um grafo via `create_agent_graph` com limite de 20 iteracoes.
5. **Monitorizacao:** Utiliza `get_openai_callback()` para registar o consumo de tokens e custos da sub-pesquisa.
6. **Extracao:** Captura o resultado estruturado da tool `search_result`.

### `create_searcher_tool`

Factory que cria uma tool LangChain para delegacao.

```python
def create_searcher_tool(
    llm: BaseChatModel,
    db_session: AsyncSession | None = None,
    execution_context: str = "",
    task: str | None = None,
    subtask: str | None = None,
) -> BaseTool:
    @tool(args_schema=ComplexSearch)
    async def search(question: str, message: str) -> str:
        # ... invoke perform_search ...
```

Esta tool e **obrigatoriamente assincrona** para evitar bloquear o event loop do agente chamador. Ela encapsula todo o estado necessario (LLM, DB session) via closure.

---

## Integracao no Generator (`src/pentest/agents/generator.py`)

O Generator foi actualizado para substituir o stub estatico pela tool real do Searcher.

```python
    llm = _resolve_generator_llm(
        provider=provider,
        model=model,
        timeout=None,
        stop=None,
    )

    # ...

    search_tool = create_searcher_tool(llm=llm, execution_context=execution_context)
    tools.extend([create_browser_tool(), memorist, search_tool, subtask_list])
```

**Alteracao Estrutural:** A resolucao do LLM foi movida para antes da criacao da lista de tools, pois o Searcher necessita de uma instancia de LLM (geralmente a mesma do agente pai) para operar o seu proprio grafo interno.

---

## Padrao de Implementacao: Agent Delegation

O Searcher estabelece o padrao de "Agente dentro de Tool":
1. O Agente A chama a tool `search`.
2. A tool `search` inicia um novo grafo LangGraph (Agente B).
3. O Agente B executa o seu loop ate atingir uma barrier tool.
4. O resultado da barrier tool do Agente B e retornado como o output da tool para o Agente A.

Isto permite uma composicao infinita e modular de especialistas.

---

## Ficheiros Alterados

| Ficheiro | Alteracao |
|---|---|
| `src/pentest/agents/base.py` | Adicao de `RetryPolicy` ao node de LLM. |
| `src/pentest/agents/searcher.py` | Implementacao do agente Searcher e factory da tool. |
| `src/pentest/agents/generator.py` | Substituicao do stub de pesquisa pela tool real. |
| `src/pentest/agents/__init__.py` | Exposicao da API publica do Searcher. |

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Searcher Agent/US-055-SEARCH-BARRIER-EXPLAINED]]
- [[Epics/Searcher Agent/US-059-SEARCH-PROMPTS-EXPLAINED]]
- [[Epics/Generator agent/US-037-BASE-GRAPH-EXPLAINED]]
