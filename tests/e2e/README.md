# tests/e2e/

Testes end-to-end com LLM real, Docker e serviços reais. Correm automaticamente no push para `main` no CI. Requerem `OPENAI_API_KEY` e `TAVILY_API_KEY`.

## Subdirectórios

| Directório | O que testa |
|---|---|
| `database/` | Migrations e modelos contra PostgreSQL real |
| `tools/` | Tavily search com API key real |

## Como correr

```bash
# Necessita variáveis de ambiente
export OPENAI_API_KEY=sk-...
export TAVILY_API_KEY=tvly-...

pytest tests/e2e/ -v -m e2e
```

## Variáveis de ambiente necessárias

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | Sim | Chave OpenAI para LLM real |
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
| `TEST_RESULTS_FINAL.md` | Registo histórico de resultados da suite E2E |
| `TEST_RESULTS_GRAPHITI_E2E.md` | Registo histórico de resultados dos testes Graphiti E2E |
