# tests/unit/graphiti/

Testes unitários de `graphiti/` — GraphitiClient e GraphitiConfig sem chamadas HTTP reais.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_client.py` | Testa `GraphitiClient`: init, os 7 métodos de search, mapeamento de modelos Pydantic |
| `test_config.py` | Testa `GraphitiConfig`: leitura de env vars, defaults, validação de URL |

## O que é testado

- `GraphitiConfig` lê `GRAPHITI_URL`, `GRAPHITI_ENABLED`, `GRAPHITI_TIMEOUT` do ambiente
- `GraphitiClient` não faz chamadas reais (HTTP mockado)
- Métodos de search passam os argumentos corretos no corpo do pedido
- Respostas são deserializadas para os tipos `GraphitiOperationResult` / listas de resultados

## Módulo de produção

`src/pentest/graphiti/` — ver `docs/Epics/Knowledge Graph/US-035-GRAPHITI-CLIENT-EXPLAINED.md`
