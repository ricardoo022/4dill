# tests/

Suite de testes do LusitAI AI Pentest. Quatro camadas mapeadas aos critérios de aceitação das User Stories.

## Camadas

| Camada | Directório | Marker | Dependências | CI |
|---|---|---|---|---|
| Unit | `unit/` | *(nenhum)* | Nenhuma | Sempre |
| Integration | `integration/` | `@pytest.mark.integration` | PostgreSQL (testcontainers), Docker | Sempre |
| Agent | `agent/` | `@pytest.mark.agent` | LLM mockado (respx) | Sempre |
| E2E | `e2e/` | `@pytest.mark.e2e` | LLM real + Docker + target | Push para `main` |

## Como correr

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v -m integration
pytest tests/agent/ -v -m agent
pytest tests/e2e/ -v -m e2e          # necessita OPENAI_API_KEY + TAVILY_API_KEY

# Teste único
pytest tests/unit/tools/test_barriers.py -v

# Cobertura (sem e2e)
pytest tests/ --ignore=tests/e2e/ --cov=src/pentest --cov-report=term-missing
```

## Convenções

- `asyncio_mode = "auto"` — sem necessidade de `@pytest.mark.asyncio`
- Se um teste falha: corrigir o código de produção, não o teste (a menos que o teste esteja errado)
- Fixtures partilhadas em `conftest.py` raiz e por camada

## Estrutura

```
tests/
    unit/           # Sem deps externas, rápidos
    integration/    # PostgreSQL real (testcontainers) + Docker
    agent/          # LLM mockado (respx)
    e2e/            # LLM real + Docker + target (corre no push para main)
    conftest.py     # Fixtures globais partilhadas
```
