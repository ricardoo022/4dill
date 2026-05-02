# tests/e2e/tools/

Testes E2E de `tools/` com serviços externos reais.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_guide_e2e.py` | Testa Guide search e store com real DB e OpenAI embeddings round-trip |
| `test_tavily_e2e.py` | Testa Tavily search com `TAVILY_API_KEY` real: answer gerada por IA, fontes rankeadas |
| `test_memorist_barrier_e2e.py` | Valida fim de ciclo por `memorist_result` e payload final estruturado (`result`, `message`) no grafo do agente |

## O que é testado

- Tavily devolve `answer` não-vazia para queries de segurança/pentest
- `search_guide` e `store_guide` round-trip: anonimização, armazenamento vetorial e recuperação semântica
- Fontes devolvidas têm URL e score válidos
- Resultado formatado correctamente para consumo pelo Searcher agent
- Fluxo e2e do Memorist: chamada de tool normal → barrier `memorist_result` → terminação do loop + extração do payload final

## Dependências

- `@pytest.mark.e2e`
- `TAVILY_API_KEY` obrigatória apenas para `test_tavily_e2e.py`
- `test_memorist_barrier_e2e.py` não depende de serviços externos

## Módulo de produção

`src/pentest/tools/tavily.py`, `src/pentest/tools/barriers.py`, `src/pentest/tools/stubs.py` — ver `docs/Epics/Searcher Agent/US-057-TAVILY-SEARCH-TOOL-EXPLAINED.md`
