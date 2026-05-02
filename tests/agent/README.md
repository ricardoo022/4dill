# tests/agent/

Testes de agentes com LLM mockado via respx. Validam o comportamento do loop de execução sem chamadas reais ao LLM. Correm em CI a cada PR.

## Como correr

```bash
pytest tests/agent/ -v -m agent
```

## Convenções

- Todos os testes têm `@pytest.mark.agent`
- LLM mockado com respx — respostas programadas com tool_calls pré-definidas
- Sem chamadas reais à API (sem `OPENAI_API_KEY` necessária)
- `asyncio_mode = "auto"` — sem `@pytest.mark.asyncio`

## O que é testado nesta camada

- Fluxo completo do loop de agente: LLM → tool_call → execute → loop
- Detecção de barriers e extracção de resultado
- Comportamento de Adviser quando `recursion_limit` é atingido
- Reflection: LLM retorna texto em vez de tool_call → Reflector corrige

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_placeholder.py` | Placeholder para smoke test da camada de agentes |
