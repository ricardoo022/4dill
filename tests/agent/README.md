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
- Searcher Agent: montagem dinâmica de tools, comportamento do barrier `search_result`, integração com Generator

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_generator_agent.py` | Testes do Generator em camada agent: plano realista, seleção de tools com/sem Docker, erro quando barrier não é atingido |
| `test_searcher_agent.py` | Testes do Searcher em camada agent: sucesso/falha do barrier, inclusão condicional de tools (DDG/Tavily/search_answer), factory async da tool de delegação e integração com Generator |
| `test_scanner.py` | Testes do Scanner em camada agent: montagem do grafo, validação de tools obrigatórias (inclui `installer`), propagação de `fase` para renderização de prompt, e erro quando `hack_result` não é atingido |
| `test_scanner_templates.py` | Testes do Scanner prompt rendering: system+user templates, injecção de FASE skill em runtime e integração com SKILL.md real do `lusitai-internal-scan` |
| `test_placeholder.py` | Placeholder para smoke test da camada de agentes |
