# tests/e2e/tools/

Testes E2E de `tools/` com serviços externos reais.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_tavily_e2e.py` | Testa Tavily search com `TAVILY_API_KEY` real: answer gerada por IA, fontes rankeadas |

## O que é testado

- Tavily devolve `answer` não-vazia para queries de segurança/pentest
- Fontes devolvidas têm URL e score válidos
- Resultado formatado correctamente para consumo pelo Searcher agent

## Dependências

- `@pytest.mark.e2e`
- `TAVILY_API_KEY` env var obrigatória

## Módulo de produção

`src/pentest/tools/tavily.py` — ver `docs/Epics/Searcher agent/US-057-TAVILY-SEARCH-TOOL-EXPLAINED.md`
