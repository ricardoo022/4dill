# tests/unit/models/

Testes unitários de `models/` — validação dos schemas Pydantic partilhados.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_search_us054.py` | Testa `SearchResult`, `SearchAction`, `ComplexSearch`, `SearchAnswerAction` (US-054) |

## O que é testado

- `SearchResult`: campos obrigatórios e opcionais, validação de URL
- `SearchAction`: criação com queries simples e compostas
- `ComplexSearch`: lista de `SearchAction`, validação de estrutura
- `SearchAnswerAction`: answer e fontes rankeadas
- Serialização/deserialização JSON round-trip

## Módulo de produção

`src/pentest/models/search.py` — ver `docs/Epics/Searcher agent/US-054-SEARCH-MODELS-EXPLAINED.md`
