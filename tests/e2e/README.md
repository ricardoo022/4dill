# tests/e2e/

Testes end-to-end com LLM real, Docker e serviços reais. Nesta repo são executados manualmente (`workflow_dispatch`) no CI. Requerem chaves de provider LLM e, conforme cenário, `TAVILY_API_KEY`.

## Subdirectórios

| Directório | O que testa |
|---|---|
| `database/` | Migrations e modelos contra PostgreSQL real |
| `tools/` | Tavily search com API key real |

## Ficheiros de e2e do Generator

| Ficheiro | O que testa |
|---|---|
| `test_generator_llm_e2e.py` | `generate_subtasks` com LLM real provider-agnostic; valida contrato de saída (1-15 subtasks, title/description, pelo menos uma `fase`) |

## Como correr

```bash
# Necessita variáveis de ambiente (exemplos)
export OPENAI_API_KEY=sk-...
# ou
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...

pytest tests/e2e/ -v -m e2e
```

## Variáveis de ambiente necessárias

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | Sim (se provider OpenAI) | Chave OpenAI para LLM real |
| `ANTHROPIC_API_KEY` | Sim (se provider Anthropic) | Chave Anthropic para LLM real |
| `GENERATOR_PROVIDER` | Opcional | Provider específico do Generator (ex: `openai`, `anthropic`) |
| `LLM_PROVIDER` | Opcional | Provider default global quando não há override por agente |
| `TAVILY_API_KEY` | Para tools/e2e | Chave Tavily para search real |
| `DATABASE_URL` | Para database/e2e | URL PostgreSQL (default: devcontainer) |
| `GRAPHITI_REAL_E2E` | Opcional | `true` activa validação estrita do Graphiti |
| `GRAPHITI_FORCE_VALIDATE` | Opcional | `true` força validação de materialização |

## Ficheiros raiz

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_graphiti_knowledge_graph.py` | Valida ingestão e pesquisa no knowledge graph Neo4j/Graphiti |
| `test_graphiti_raw_text_to_graph.py` | Testa pipeline raw text → entidades → grafo |
| `test_real_materialization.py` | Valida materialização de episódios no Graphiti |
| `test_real_pentest_scenarios.py` | Cenários reais de pentest contra targets vulneráveis |
| `tools/test_memorist_barrier_e2e.py` | Valida comportamento e2e de barrier: terminação por `memorist_result` + payload final estruturado |
| `TEST_RESULTS_FINAL.md` | Registo histórico de resultados da suite E2E |
| `TEST_RESULTS_GRAPHITI_E2E.md` | Registo histórico de resultados dos testes Graphiti E2E |
