---
tags: [knowledge-graph, docker]
---

# Graphiti Troubleshooting (Devcontainer)

Esta nota documenta os erros observados durante a validacao E2E do Graphiti e como resolver rapidamente no ambiente local.

## Sintomas observados

- `POST /search` retorna `500 Internal Server Error`.
- Testes E2E de `tests/e2e/test_graphiti_knowledge_graph.py` falham ou ficam em `SKIPPED` por "service not reachable".
- Container Graphiti aparece como `Up (unhealthy)`.
- Logs mostram `Illegal header value b'Bearer '` e `openai.APIConnectionError`.
- Dentro do `app`, `graphiti` pode nao resolver por DNS (`Could not resolve host: graphiti`).

## Causas raiz identificadas

1. `OPENAI_API_KEY` ausente ou vazia no servico `graphiti`.
2. Healthcheck a apontar para `/health` (404) em vez de `/healthcheck` (200).
3. Stack docker inconsistente (servicos fora da mesma rede compose), causando falha de resolucao DNS entre `app` e `graphiti`.
4. Execucao de testes fora do ambiente correto (Python 3.10 sem dependencias dev), levando a erros como `ModuleNotFoundError: pytest_asyncio`.

## Correcao recomendada

### 1) Corrigir compose do Graphiti

No ficheiro `.devcontainer/docker-compose.yml`:

- manter apenas uma entrada de `OPENAI_API_KEY` no bloco `environment` do `graphiti`;
- usar healthcheck em `/healthcheck`.

Exemplo:

```yaml
graphiti:
  environment:
    OPENAI_API_KEY: ${OPENAI_API_KEY:-}
  healthcheck:
    test:
      [
        "CMD",
        "python",
        "-c",
        "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthcheck').status == 200 else 1)",
      ]
```

### 2) Recriar apenas o Graphiti

```bash
export OPENAI_API_KEY='sk-...'
docker compose -f .devcontainer/docker-compose.yml up -d --force-recreate graphiti
```

### 3) Garantir ambiente de testes no `app`

```bash
docker compose -f .devcontainer/docker-compose.yml exec app bash -lc 'cd /workspaces/lusitai-aipentest && pip install -e ".[dev]"'
```

### 4) Validar conectividade interna

```bash
docker compose -f .devcontainer/docker-compose.yml exec app bash -lc 'curl -sS http://graphiti:8000/healthcheck'
```

Se houver `Could not resolve host: graphiti`, subir `app` e `graphiti` na mesma stack/rede do compose:

```bash
docker compose -f .devcontainer/docker-compose.yml up -d db graphiti app
```

### 5) Reexecutar teste E2E alvo

```bash
docker compose -f .devcontainer/docker-compose.yml exec app bash -lc 'cd /workspaces/lusitai-aipentest && GRAPHITI_URL=http://graphiti:8000 GRAPHITI_FORCE_VALIDATE=true PYTHONPATH="$PWD/src" pytest tests/e2e/test_graphiti_knowledge_graph.py::test_graphiti_e2e_recent_context_search_returns_seeded_host -v -m e2e --tb=short -rs'
```

## Observacoes operacionais

- Se uma API key tiver sido exposta em terminal/chat, revogar imediatamente e criar nova key.
- O facto de `GET /healthcheck` responder 200 nao garante que `/search` esteja funcional; o endpoint de search depende de embeddings e conectividade externa configurada.

## Related Notes

- [[Epics/Knowledge Graph/US-034-NEO4J-GRAPHITI-DEVCONTAINER-EXPLAINED]]
- [[Epics/Knowledge Graph/US-035-GRAPHITI-CLIENT-EXPLAINED]]
- [[Epics/Knowledge Graph/US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED]]
- [[DATABASE-SCHEMA]]
- [Docs Home](../../README.md)
