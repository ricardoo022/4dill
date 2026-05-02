# tests/integration/tools/

Testes de integração de `tools/` que requerem acesso à rede ou serviços externos.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_duckduckgo_integration.py` | Testa DuckDuckGo search com pedidos HTTP reais |

## O que é testado

- DuckDuckGo devolve resultados reais para queries de teste
- Resultados formatados correctamente (título, URL, snippet)
- Truncation actua quando resultados excedem o limite de tamanho
- Timeout e erros de rede retornam mensagem de erro gracioso, sem raise

## Dependências

- `@pytest.mark.integration`
- Acesso à internet (DuckDuckGo API pública, sem chave)

## Módulo de produção

`src/pentest/tools/duckduckgo.py` — ver `docs/Epics/Searcher agent/US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED.md`
