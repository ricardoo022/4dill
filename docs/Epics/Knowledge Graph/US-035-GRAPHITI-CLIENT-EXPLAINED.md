---
tags: [knowledge-graph]
---

# US-035: Graphiti Client — Explicacao Detalhada

Este documento explica a implementacao do client Python para o Graphiti API, criado para a `US-035`.

---

## Objetivo da US

O objetivo desta story e dar ao sistema um client HTTP reutilizavel para:

- enviar mensagens dos agentes para o Graphiti
- pesquisar relacoes guardadas no knowledge graph
- funcionar em modo disabled sem quebrar o resto da aplicacao
- devolver resultados tipados em vez de `dict` solto

Esta story prepara a base para a tool `graphiti_search` da `US-036`.

---

## Ficheiros criados ou alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/graphiti/client.py` | Client async HTTP para o Graphiti |
| `src/pentest/graphiti/models.py` | Models Pydantic de request/response |
| `src/pentest/graphiti/__init__.py` | Exports publicos do package |
| `src/pentest/graphiti/README.md` | Atualiza a documentacao do modulo |
| `tests/unit/graphiti/test_client.py` | Testes unitarios mockados do client |

---

## 1. Porque existe um client dedicado

Em vez de espalhar `httpx.AsyncClient` pelo codigo todo, foi criado um wrapper unico:

- centraliza o URL e timeout
- esconde detalhes da API REST do Graphiti
- uniformiza erros e respostas
- facilita mocking em testes
- deixa a integracao injectavel para os agentes e tools futuras

Isto e importante porque a story pede explicitamente dependency injection e no-op quando Graphiti esta disabled.

---

## 2. `GraphitiClient`

### Local

O client vive em:

`src/pentest/graphiti/client.py`

### Construtor

```python
GraphitiClient(
    url: str,
    timeout: float = 30.0,
    enabled: bool = False,
    default_group_id: str = "default",
    http_client: httpx.AsyncClient | None = None,
)
```

### O que cada parametro faz

- `url` define a base do Graphiti API
- `timeout` define o timeout default por request
- `enabled` controla se o client opera de verdade ou em modo disabled
- `default_group_id` define o group usado quando nenhum e passado
- `http_client` permite injectar um `AsyncClient` externo para testes ou composicao

### Porque existe tambem `create()`

```python
client = await GraphitiClient.create(...)
```

O construtor em Python nao pode fazer `await`, por isso foi criado um factory async. E este metodo que:

- instancia o client
- corre o health check se `enabled=True`

Isto cumpre o acceptance criterion:

> Se `enabled=True`, verifica health check no init

---

## 3. Health check

### Metodo

```python
await client.ensure_healthy()
```

### Comportamento

- se `enabled=False`, retorna logo sem erro
- se ja foi validado antes, nao repete
- tenta primeiro `/healthcheck`
- se receber `404`, tenta `/health`
- levanta erro claro em caso de timeout ou falha de ligacao

### Porque ha fallback entre `/healthcheck` e `/health`

O setup do `US-034` usou `/health` no Docker health check, enquanto o Graphiti upstream atual expõe `/healthcheck` no server FastAPI.

Por isso o client foi feito para aceitar os dois caminhos. Isto reduz fragilidade entre:

- a imagem atual do Docker
- futuras versoes do Graphiti
- diferencas entre documentacao e runtime real

---

## 4. Modo disabled

### Regra geral

Quando `enabled=False`:

- `add_messages()` faz no-op e devolve sucesso
- os metodos de search levantam `GraphitiNotEnabledError`

### Porque a ingestao faz no-op

O acceptance criterion diz:

> Se `enabled=False`, todas as operacoes retornam sem erro (no-op)

Para ingestao isto encaixa bem: o sistema pode continuar a correr e simplesmente ignorar a escrita no graph.

### Porque a search levanta erro

Os testes da story pedem explicitamente:

> `GraphitiClient(enabled=False)` → `temporal_search()` retorna erro "not enabled"

Por isso o design final ficou:

- mutacoes: no-op
- leitura/pesquisa: erro claro

Assim, o chamador sabe imediatamente que tentou consultar uma integracao desligada.

---

## 5. `add_messages()`

### Metodo

```python
await client.add_messages(messages, group_id="default")
```

### O que faz

Este metodo envia um payload para:

`POST /messages`

O payload inclui:

- `group_id`
- lista de mensagens normalizadas

### Normalizacao das mensagens

As mensagens entram como:

- `GraphitiMessage`
- ou `dict` compatível

O client converte tudo para `GraphitiMessage`, que garante:

- `uuid`
- `timestamp`
- `role`
- `content`

### Porque isto importa

Sem esta normalizacao, cada chamador teria de montar manualmente o JSON, o que:

- duplica logica
- aumenta risco de payloads incompletos
- dificulta testes

---

## 6. Os 7 metodos de search

Foram implementados os 7 metodos pedidos pela story:

- `temporal_search()`
- `entity_relationship_search()`
- `diverse_search()`
- `episode_context_search()`
- `successful_tools_search()`
- `recent_context_search()`
- `entity_by_label_search()`

### Como estes metodos funcionam por baixo

Todos fazem wrapping sobre um metodo interno:

```python
await self._search(...)
```

que envia:

`POST /search`

### Porque existe um unico endpoint de search

Na API atual do Graphiti upstream, a pesquisa e exposta por um endpoint generico `/search`, nao por 7 endpoints diferentes.

Por isso a implementacao fez o seguinte:

- cada metodo monta um `query` com hints especificos
- todos passam pelo mesmo endpoint HTTP
- o chamador continua a ter uma interface Python expressiva e tipada

Exemplos:

- `temporal_search()` acrescenta uma hint de janela temporal
- `entity_relationship_search()` acrescenta o `center_node_uuid` e `max_depth`
- `entity_by_label_search()` acrescenta os labels alvo
- `successful_tools_search()` acrescenta o numero minimo de mencoes

Isto preserva a API que o resto do projeto espera, mesmo que o servidor real tenha uma superficie REST mais pequena.

---

## 7. Models Pydantic

### `GraphitiMessage`

Representa uma mensagem/episode enviada para ingestao.

Campos principais:

- `content`
- `role`
- `role_type`
- `uuid`
- `timestamp`
- `source_description`

Inclui um helper:

```python
to_api_dict()
```

que converte para o formato JSON esperado pelo Graphiti.

### `GraphitiOperationResult`

Representa o retorno de operacoes mutativas, como `add_messages()`.

Tem:

- `success`
- `message`

O campo `message` ficou com default vazio para tolerar respostas mais minimalistas do Graphiti.

### `GraphitiNodeResult`

Representa nodes devolvidos por pesquisa, para compatibilidade com evolucoes futuras da API.

### `GraphitiEdgeResult`

Representa facts/edges devolvidos por pesquisa.

Campos principais:

- `uuid`
- `name`
- `fact`
- `valid_at`
- `invalid_at`
- `created_at`
- `expired_at`

### `GraphitiSearchResponse`

Normaliza a resposta de search para um formato estavel:

- `nodes`
- `edges`

Tambem expõe:

```python
result.facts
```

como alias para `edges`, porque a API do Graphiti atual tende a devolver `facts`.

---

## 8. Tratamento de erros

Foram criadas exceptions especificas:

- `GraphitiError`
- `GraphitiNotEnabledError`
- `GraphitiConnectionError`
- `GraphitiTimeoutError`

### Porque isto melhora o codigo

Em vez de deixar `httpx` vazar diretamente para todo o sistema:

- o dominio Graphiti passa a ter erros semanticos proprios
- o chamador pode reagir por tipo de erro
- os testes ficam muito mais claros

Exemplo:

```python
except GraphitiTimeoutError:
    ...
```

em vez de depender de detalhes do `httpx`.

---

## 9. Testes unitarios

### Ficheiro

`tests/unit/graphiti/test_client.py`

### O que foi coberto

- `enabled=False` em `add_messages()` devolve sucesso sem chamar rede
- `enabled=False` em `temporal_search()` levanta `GraphitiNotEnabledError`
- `create(enabled=True)` passa quando o health check responde 200
- URL invalido falha com `GraphitiConnectionError`
- `add_messages()` envia o payload esperado
- os 7 metodos de search devolvem resultados tipados
- timeout em search levanta `GraphitiTimeoutError`

### Porque usar `respx`

`respx` permite mockar `httpx` diretamente, o que encaixa muito bem neste client:

- nao precisamos de Graphiti real para unit tests
- conseguimos validar o JSON enviado
- conseguimos simular timeout e connection errors com precisao

---

## 10. Compatibilidade com a API oficial atual

Esta implementacao foi guiada pela API atual do Graphiti upstream:

- ingestao em `POST /messages`
- pesquisa em `POST /search`
- health check em `/healthcheck`

Foi adicionado fallback para `/health` porque o `US-034` ja estava montado com esse caminho no compose/health check.

Isto significa que o client esta preparado tanto para:

- a imagem/documentacao upstream atual
- pequenas diferencas de deployment local

---

## 11. O que falta para as proximas stories

Depois desta US, o projeto fica com:

- um client Graphiti real e injectavel
- results tipados
- tratamento de erros semantico
- testes unitarios mockados

O passo seguinte natural e a `US-036`, onde este client sera usado por uma tool `graphiti_search` dentro do fluxo dos agentes.

---

## Limites desta implementacao

Esta story ainda nao faz:

- integration tests reais contra um container Graphiti vivo
- ligacao do client ao controller/tools/agents
- enriquecimento de payloads com metadados de scan mais avancados

Essas pecas pertencem a stories seguintes do Epic.

---

## Related Notes

- [Docs Home](../../README.md)
- [[PROJECT-STRUCTURE]]
- [[DATABASE-SCHEMA]]
- [[US-034-NEO4J-GRAPHITI-DEVCONTAINER-EXPLAINED]]
- [[US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED]]
