---
tags: [agents]
---

# US-065: Scanner Agent Completo — Explicação Detalhada

Este documento detalha a implementação do Scanner Agent completo, incluindo sua fiação (wiring), ferramentas, barreiras e loop de execução utilizando LangGraph.

O Scanner Agent é a unidade de execução técnica do LusitAI, responsável por realizar tarefas de pentesting dentro de containers Docker.

## Contexto

O Scanner Agent é o equivalente funcional do `pentester` no PentAGI. Ele recebe uma tarefa específica (subtask), carrega o contexto operacional necessário, injecta instruções de fase (FASE skills) e executa um loop de pensamento e ação até atingir um resultado conclusivo.

## Ficheiros Alterados

| Ficheiro | Descrição |
| --- | --- |
| `src/pentest/models/tool_args.py` | Adição do contrato `ScannerAction` para delegação. |
| `src/pentest/tools/stubs.py` | Adição de stubs para agentes especialistas (coder, installer, adviser, maintenance). |
| `src/pentest/agents/scanner.py` | Implementação principal do grafo e função de execução do Scanner. |
| `src/pentest/agents/__init__.py` | Re-exportação do Scanner Agent. |

---

## Implementação

### ScannerAction Model (`src/pentest/models/tool_args.py`)

O `ScannerAction` define o contrato de entrada para tarefas delegadas ao Scanner.

```python
class ScannerAction(BaseModel):
    """Schema for scanner tool calls (delegation)."""

    question: str = Field(..., description="Detailed task for the scanner in English")
    message: str = Field(..., description="Short internal summary of the task")
```

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `question` | `str` | A tarefa detalhada que o agente deve realizar. |
| `message` | `str` | Um resumo curto para logs e acompanhamento humano. |

---

### Scanner Graph (`src/pentest/agents/scanner.py`)

O Scanner utiliza `create_agent_graph` para montar seu loop de execução.

#### create_scanner_graph

Esta função monta o conjunto de ferramentas e o grafo de estados do LangGraph.

```python
async def create_scanner_graph(
    llm: BaseChatModel,
    docker_client: DockerClient,
    container_id: str,
    db_session: AsyncSession | None = None,
    graphiti_client: GraphitiClient | None = None,
    max_iterations: int = 100,
) -> Any:
    # ... (ferramentas core e condicionais)
    return create_agent_graph(
        llm=llm,
        tools=tools,
        barrier_names={"hack_result"},
        max_iterations=max_iterations,
    )
```

**Ferramentas Incluídas:**
- **Core:** `hack_result`, `adviser`, `coder`, `maintenance`, `memorist`, `searcher`, `terminal`, `file`.
- **Condicionais:** `browser`, `sploitus`, `search_guide`, `store_guide`, `graphiti_search`.

---

### Como Executar os Testes

Para validar a implementação do Scanner Agent:

```bash
pytest tests/agent/test_scanner.py -v
```

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Scanner Agent/US-064-SCANNER-TEMPLATES-EXPLAINED]]
