# tests/unit/tools/

Testes unitários de `tools/` — todas as tool factories e handlers com dependências mockadas.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_barriers.py` | Testa `subtask_list`, `search_result`, `memorist_result` e `hack_result` — validação de schemas e detecção de barriers pelo `BarrierAwareToolNode` |
| `test_browser.py` | Testa `BrowserTool`: fetch HTTP mockado, parse markdown/HTML, fallback parsers |
| `test_duckduckgo.py` | Testa tool DuckDuckGo: resultados formatados, truncation, availability check |
| `test_graphiti_search.py` | Testa `create_graphiti_search_tool()` e `create_mock_graphiti_search_tool()` |
| `test_guide.py` | Testa `search_guide` e `store_guide` — anonimização, deduplicação e threshold filtering |
| `test_sploitus.py` | Testa `sploitus_search` — integração mockada com Sploitus API |
| `test_stubs.py` | Testa `memorist` e `searcher` stubs — retornam mensagens graciosas |
| `test_tavily.py` | Testa tool Tavily: answer, fontes rankeadas, API key check |
| `test_terminal_file.py` | Testa `create_terminal_tool()` e `create_file_tool()` — closures com docker_client mockado |

## O que é testado

- Barriers são detectadas pelo nome (`subtask_list`, `search_result`, `memorist_result`, `hack_result`) e os seus args extraídos para `barrier_result`
- `memorist_result` valida payload estruturado (`result` + `message`) e integra correctamente no estado final do grafo
- `BrowserTool` retorna string (nunca raise) — erros devolvidos como texto ao LLM
- DuckDuckGo e Tavily: sem API key ou serviço indisponível → mensagem de erro, não exception
- `create_terminal_tool(docker_client, container_id)` injeta docker_client via closure
- `create_file_tool(docker_client, container_id)` segue o mesmo padrão

## Módulo de produção

`src/pentest/tools/` — ver `docs/Epics/Generator agent/` e `docs/Epics/Searcher Agent/`
