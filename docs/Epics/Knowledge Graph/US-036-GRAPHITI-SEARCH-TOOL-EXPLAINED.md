---
tags: [knowledge-graph]
---

# US-036: Graphiti Search Tool Handler — Explicacao Detalhada

Este documento explica a implementacao da tool `graphiti_search` criada para a `US-036`.

---

## Objetivo da US

O objetivo desta story e expor o knowledge graph aos agentes atraves de uma tool simples:

- o agente chama `graphiti_search`
- passa `search_type` + `query` + parametros opcionais
- o handler escolhe o metodo certo do `GraphitiClient`
- devolve texto legivel, nunca JSON raw

Isto e a ponte entre a `US-035` (client HTTP) e o uso real do knowledge graph dentro dos agentes.

---

## Ficheiros criados ou alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/models/tool_args.py` | Novo schema `GraphitiSearchAction` |
| `src/pentest/tools/graphiti_search.py` | Handler principal da tool |
| `src/pentest/tools/registry.py` | Registry minimo com metadata da tool |
| `src/pentest/tools/__init__.py` | Exports publicos da tool e registry |
| `src/pentest/tools/README.md` | Atualiza a documentacao do modulo |
| `tests/unit/tools/test_graphiti_search.py` | Testes unitarios da tool |

---

## 1. `GraphitiSearchAction`

Foi criado um schema Pydantic com:

- `search_type`
- `query`
- `recency_window`
- `center_node_uuid`
- `max_depth`
- `diversity_level`
- `min_mentions`
- `node_labels`
- `message`

### Porque `search_type` e `str` e nao `Literal`

O schema continua a expor um enum no JSON schema, mas o tipo em runtime ficou `str`.

Isto foi uma decisao intencional:

- o registry continua a mostrar os valores permitidos
- o handler consegue devolver erro claro quando o valor e invalido
- evitamos que a validacao do Pydantic rebente antes da tool devolver uma mensagem amigavel ao agente

---

## 2. `graphiti_search` tool

O handler vive em:

`src/pentest/tools/graphiti_search.py`

Foi implementado como factory:

```python
create_graphiti_search_tool(graphiti_client)
```

Isto segue o mesmo padrao de `terminal`, `file` e `browser`: a dependencia e injectada por closure.

---

## 3. Mapping entre `search_type` e `GraphitiClient`

O handler aceita 6 `search_type`s:

- `recent_context`
- `successful_tools`
- `episode_context`
- `entity_relationships`
- `diverse_results`
- `entity_by_label`

### Mapping implementado

- `recent_context` → `client.recent_context_search()`
- `successful_tools` → `client.successful_tools_search()`
- `episode_context` → `client.episode_context_search()`
- `entity_relationships` → `client.entity_relationship_search()`
- `diverse_results` → `client.diverse_search()`
- `entity_by_label` → `client.entity_by_label_search()`

Isto cumpre a ideia da story: o agente usa uma interface pequena e coerente, enquanto o handler traduz para a API real do client.

---

## 4. Graceful disable

Se o client tiver `enabled=False`, a tool retorna:

`Knowledge graph not enabled`

Sem crash, sem exception visivel ao agente.

Tambem existe tratamento para `GraphitiNotEnabledError`, para manter o mesmo comportamento mesmo que o client sinalize o estado via exception.

---

## 5. Erros claros por tipo

A tool devolve erros legiveis quando faltam parametros obrigatorios por tipo:

- `entity_relationships` exige `center_node_uuid`
- `entity_by_label` exige `node_labels`

E devolve erro claro para `search_type` invalido:

`graphiti_search tool error: invalid search_type '...'`

Isto ajuda o LLM a corrigir a chamada seguinte em vez de entrar em crash.

---

## 6. Formato do resultado

Foi criado um formatter interno que devolve texto em vez de JSON.

Estrutura tipica:

- linha de cabecalho com o tipo de pesquisa e query
- secao `Facts:`
- secao `Entities:` quando existirem nodes

Exemplo:

```text
Knowledge graph results for recent_context and query 'nmap results':
Facts:
1. Port 443 runs nginx 1.24
Relation: runs_on
```

Isto cumpre o acceptance criterion:

> Resultado formatado como texto legível para o agente

---

## 7. Registry minimo

Como a infraestrutura completa de registry ainda nao esta implementada no projeto, foi criado um registry minimo e testavel em:

`src/pentest/tools/registry.py`

Com:

- `SearchVectorDbToolType = "search_vector_db"`
- `ToolDefinition`
- `GRAPHITI_SEARCH_TOOL_DEFINITION`
- `TOOL_REGISTRY`

Isto permite:

- associar a tool ao tipo `SearchVectorDbToolType`
- expor o JSON schema da tool
- ter uma base pequena mas real para integracao futura

---

## 8. Testes unitarios

O ficheiro:

`tests/unit/tools/test_graphiti_search.py`

cobre:

- schema com enum de `search_type`
- tool registada no registry com JSON schema
- mapping de `recent_context`
- mapping de `entity_relationships`
- comportamento com Graphiti disabled
- erro claro com `search_type` invalido
- output em texto legivel

Os testes usam `AsyncMock` para validar exatamente que metodo do client foi chamado.

---

## 9. O que esta pronto depois desta US

Depois da `US-036`, o projeto passa a ter:

- client Graphiti real
- tool handler para agentes
- schema validado
- registry minimo para metadata da tool
- testes da integracao entre tool e client

Isto desbloqueia o uso do knowledge graph dentro dos agentes do Epic 7.

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[US-034-NEO4J-GRAPHITI-DEVCONTAINER-EXPLAINED]]
- [[US-035-GRAPHITI-CLIENT-EXPLAINED]]
