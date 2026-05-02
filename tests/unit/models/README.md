# tests/unit/models/

Testes unitários de `models/` — validação dos schemas Pydantic partilhados.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_hack.py` | Testa `ExploitInfo` e `PayloadConfig` — validação de payloads e exploits |
| `test_search_us054.py` | Testa `SearchResult`, `SearchAction`, `ComplexSearch`, `SearchAnswerAction` (US-054) |
| `test_memorist_models.py` | Testa `MemoristResult`: campos obrigatórios, rejeição de vazio/whitespace e trim automático |

## O que é testado

- `ExploitInfo`: validação de campos de exploit (CVE, target, etc.)
- `PayloadConfig`: validação de payloads complexos
- `SearchResult`: campos obrigatórios e opcionais, validação de URL
- `SearchAction`: criação com queries simples e compostas
- `ComplexSearch`: lista de `SearchAction`, validação de estrutura
- `SearchAnswerAction`: answer e fontes rankeadas
- `MemoristResult`: contrato final (`result` + `message`), validação non-empty e normalização por trim
- Serialização/deserialização JSON round-trip

## Módulo de produção

`src/pentest/models/search.py` — ver `docs/Epics/Searcher Agent/US-054-SEARCH-MODELS-EXPLAINED.md`
