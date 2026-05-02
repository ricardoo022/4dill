---
tags: [agents]
---

# US-055: `search_result` Barrier Tool — Explicacao Detalhada

Este documento explica, em detalhe, a implementacao da `US-055` no Searcher epic: o barrier tool `search_result`, como ele funciona com o `create_agent_graph`, e porque a logica principal nao fica dentro da funcao da tool.

---

## Objetivo da US-055

A `US-055` cria o **sinal formal de termino** do Searcher.

Sem este barrier, o agente pode continuar em loop de tool calls sem um contrato claro de "resposta final entregue".
Com o barrier:

1. o LLM chama `search_result(...)` quando terminou;
2. o graph deteta que essa tool e terminal;
3. os argumentos da tool viram `state["barrier_result"]`;
4. o fluxo termina.

---

## Ficheiros envolvidos

| Ficheiro | Papel |
|---|---|
| `src/pentest/tools/barriers.py` | Define o tool `search_result` (e coexistencia com `subtask_list`) |
| `src/pentest/agents/base.py` | Implementa a deteccao de barrier (`BarrierAwareToolNode`) e encerramento do loop |
| `src/pentest/models/search.py` | Define `SearchResult` usado em `args_schema` |
| `tests/unit/tools/test_barriers.py` | Prova comportamento da tool, schema e integracao no graph |
| `docs/USER-STORIES.md` | Requisitos e acceptance criteria da US-055 |

---

## 1) Implementacao da tool em `barriers.py`

### Codigo essencial

```python
from pentest.models.search import SearchResult

@tool(args_schema=SearchResult)
def search_result(result: str, message: str) -> str:
    """Submit the final Searcher answer to end the agent loop."""
    return "search result successfully processed"
```

### O que cada parte resolve

1. `@tool(args_schema=SearchResult)`
   - Liga a tool ao model Pydantic da US-054.
   - Gera JSON schema para function calling.
   - Valida os campos obrigatorios (`result`, `message`) antes da execucao.

2. Assinatura `search_result(result: str, message: str)`
   - Explicita o contrato de saida final do Searcher:
     - `result`: resposta tecnica detalhada
     - `message`: resumo curto interno para handoff/orquestração

3. Retorno fixo `"search result successfully processed"`
   - E um **ack protocolar**, nao o payload final de negocio.
   - O valor de negocio real vem dos **args da tool call**, capturados no graph.

---

## 2) Porque a tool e "simples" por design

No padrao deste projeto, barrier tools nao fazem processamento pesado.
Elas existem para:

1. forcar output estruturado (via `args_schema`);
2. sinalizar fim de etapa;
3. permitir ao graph extrair resultado final de forma deterministica.

Isto separa responsabilidades:

- **Tool**: valida contrato + sinal de termino
- **Graph runtime**: decide parar e extrair `barrier_result`

---

## 3) Integracao com `create_agent_graph` (`agents/base.py`)

### Fluxo tecnico

O `BarrierAwareToolNode` envolve o `ToolNode` do LangGraph e, apos executar as tools, verifica os `tool_calls` da ultima `AIMessage`.

Quando encontra uma tool cujo nome esta em `barrier_names`, ele:

1. define `barrier_result = tc["args"]`
2. retorna `barrier_hit = True`
3. o router `route_after_tools` devolve `END`

Trecho chave:

```python
if tc["name"] in self.barrier_names:
    barrier_result = tc["args"]
    break
```

e depois:

```python
if state.get("barrier_hit"):
    return END
```

### Implicacao pratica

Para o Searcher, quando o LLM chama `search_result`, o estado final fica tipicamente:

```python
{
  "barrier_hit": True,
  "barrier_result": {
    "result": "...detailed report...",
    "message": "...short summary..."
  }
}
```

Ou seja, o output final e os argumentos validados da tool call.

---

## 4) Coexistencia com `subtask_list`

`barriers.py` agora contem dois barriers:

1. `subtask_list` (Generator epic)
2. `search_result` (Searcher epic)

Nao ha conflito porque o graph decide qual e terminal por configuracao local de cada agente:

- Generator usa `barrier_names=["subtask_list"]`
- Searcher usa `barrier_names=["search_result"]`

Mesma infraestrutura, nomes diferentes, contratos diferentes.

---

## 5) Cobertura de testes da US-055

Em `tests/unit/tools/test_barriers.py`, a US-055 fica coberta em quatro frentes:

1. `test_search_result_validation`
   - valida constraints do `SearchResult` (sem vazios/whitespace)

2. `test_search_result_tool`
   - garante retorno exato da tool:
   - `"search result successfully processed"`

3. `test_search_result_tool_json_schema`
   - garante schema com `result` e `message` em `properties` e `required`

4. `test_graph_integration_with_search_result`
   - mock de LLM com tool call `search_result`
   - valida `barrier_hit=True`
   - valida extracao de `state["barrier_result"]["result"]`
   - valida extracao de `state["barrier_result"]["message"]`

Adicionalmente, os testes existentes de `subtask_list` continuam a passar, cobrindo regressao de coexistencia.

---

## 6) Mapeamento direto aos Acceptance Criteria

| Acceptance Criterion (US-055) | Evidencia |
|---|---|
| `search_result` com `args_schema=SearchResult` | `src/pentest/tools/barriers.py` |
| Recebe `result` e `message` | assinatura da funcao + schema |
| Retorna string exata | `test_search_result_tool` |
| Usada com `barrier_names={"search_result"}` | `test_graph_integration_with_search_result` |
| JSON schema compativel com function calling | `test_search_result_tool_json_schema` |
| Coexiste com `subtask_list` sem conflitos | testes de `subtask_list` e `search_result` no mesmo modulo |

---

## 7) Limites intencionais da US-055

A US-055 **nao** implementa:

1. composicao completa do Searcher agent;
2. ferramentas de pesquisa web (US-056/US-057);
3. vector DB lookup (US-058);
4. wiring completo de delegacao entre agentes (US-060).

Ela prepara o bloco terminal do protocolo. O wiring completo vem nas stories seguintes.

---

## 8) Resumo arquitetural

`search_result` e uma tool curta, mas arquiteturalmente critica:

- formaliza o contrato final do Searcher;
- impede encerramento ambiguo;
- transforma fim de loop em evento observavel (`barrier_hit`);
- entrega resultado final estruturado e validado (`barrier_result`).

Por isso, a simplicidade da funcao e proposital: a "inteligencia" de termino esta no graph.

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[US-054-SEARCH-MODELS-EXPLAINED]]
- [[US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED]]
- [[US-057-TAVILY-SEARCH-TOOL-EXPLAINED]]
