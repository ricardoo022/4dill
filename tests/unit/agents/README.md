# tests/unit/agents/

Testes unitários de `agents/` — padrão base e factory concreta do Memorist.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_base.py` | Testa `AgentState`, `BarrierAwareToolNode`, `create_agent_graph` |
| `test_memorist.py` | Testa `create_memorist_agent()` e garante reutilização do contrato base com barrier `memorist_result` |

## O que é testado

- `create_agent_graph` cria um `StateGraph` com os 2 nodes corretos (`call_llm`, `execute_tools`)
- `BarrierAwareToolNode` detecta barrier tool calls e extrai os seus argumentos como resultado
- Routing condicional: tool calls → execute → barrier check → loop ou END
- `recursion_limit` impede loops infinitos
- Memorist agent usa o mesmo framework base e termina com payload estruturado via `memorist_result`

## Módulo de produção

`src/pentest/agents/base.py`, `src/pentest/agents/memorist.py` — ver `docs/Epics/Generator agent/US-037-BASE-GRAPH-EXPLAINED.md`
