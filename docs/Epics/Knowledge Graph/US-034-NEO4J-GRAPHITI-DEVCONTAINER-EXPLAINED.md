---
tags: [knowledge-graph]
---

# US-034: Neo4j + Graphiti no Dev Container — Explicacao Detalhada

Este documento explica o codigo e a configuracao adicionados para a `US-034`, que introduz Neo4j e Graphiti no ambiente de desenvolvimento local.

---

## Objetivo da US

O objetivo desta story e permitir que qualquer developer faca rebuild do dev container e tenha um ambiente local com:

- Neo4j a correr para guardar o knowledge graph
- Graphiti API a correr para extrair entidades e relacoes a partir de texto
- configuracao explicita por variaveis de ambiente
- comportamento seguro quando `GRAPHITI_ENABLED=false`

Esta story nao implementa ainda o client HTTP do Graphiti. O foco aqui e deixar a infraestrutura pronta e a configuracao base preparada para o `US-035`.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `.devcontainer/devcontainer.json` | Expõe env vars do Graphiti/Neo4j ao container da app e faz port forwarding |
| `.devcontainer/docker-compose.yml` | Sobe os containers `neo4j` e `graphiti` com health checks e configuracao de rede |
| `.env.example` | Documenta as env vars da integracao |
| `src/pentest/graphiti/config.py` | Implementa leitura tipada de `GRAPHITI_ENABLED`, `GRAPHITI_URL` e `GRAPHITI_TIMEOUT` |
| `src/pentest/graphiti/__init__.py` | Exporta a configuracao publica do package |
| `src/pentest/graphiti/README.md` | Atualiza a documentacao do modulo |
| `tests/unit/test_devcontainer_config.py` | Valida a configuracao do dev container e dos novos servicos |
| `tests/unit/graphiti/test_config.py` | Testa parsing e defaults da configuracao Graphiti |

---

## 1. Dev Container

### `.devcontainer/devcontainer.json`

Foram adicionadas novas variaveis em `containerEnv`:

```json
"GRAPHITI_ENABLED": "true",
"GRAPHITI_URL": "http://graphiti:8000",
"GRAPHITI_TIMEOUT": "30",
"NEO4J_URI": "bolt://neo4j:7687",
"NEO4J_USER": "neo4j",
"NEO4J_PASSWORD": "changeme"
```

### Porque estas variaveis existem

- `GRAPHITI_ENABLED` controla se o sistema deve tentar usar Graphiti
- `GRAPHITI_URL` define o endpoint HTTP interno da API
- `GRAPHITI_TIMEOUT` define um timeout base para requests futuras do client
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` configuram a ligacao ao Neo4j

Tambem foram adicionadas portas ao `forwardPorts`:

```json
[5432, 7474, 7687, 8000]
```

Isto permite aceder facilmente a:

- `localhost:7474` para o browser do Neo4j
- `localhost:7687` para ligacoes Bolt
- `localhost:8000` para a API do Graphiti

---

## 2. Docker Compose

### Service `neo4j`

Foi adicionado um servico:

```yaml
neo4j:
  image: neo4j:community
```

### O que este service faz

- usa a edicao Community do Neo4j
- expõe as portas `7474` e `7687`
- persiste dados em `neo4j-data`
- recebe credenciais via `NEO4J_AUTH`
- define um `healthcheck` com `cypher-shell`

### Porque o health check usa `cypher-shell`

Nao basta o container estar em estado "running". Queremos confirmar que:

- o processo do Neo4j arrancou
- a base de dados aceita autenticacao
- ja responde a uma query simples

Por isso o health check executa:

```sh
cypher-shell -u neo4j -p changeme 'RETURN 1;'
```

Se esta query passar, significa que o service esta realmente pronto para ser usado.

---

### Service `graphiti`

Tambem foi adicionado:

```yaml
graphiti:
  image: zepai/graphiti:latest
```

### O que este service faz

- arranca a API do Graphiti
- liga-se ao Neo4j usando as env vars configuradas
- expõe a porta `8000`
- espera que `neo4j` esteja healthy antes de arrancar
- faz health check ao endpoint HTTP `/health`

### Env vars passadas ao Graphiti

```yaml
NEO4J_URI: ${NEO4J_URI:-bolt://neo4j:7687}
NEO4J_PORT: "7687"
NEO4J_USER: ${NEO4J_USER:-neo4j}
NEO4J_PASSWORD: ${NEO4J_PASSWORD:-changeme}
GRAPHITI_PORT: "8000"
ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
OPENAI_API_KEY: ${OPENAI_API_KEY:-}
```

As chaves LLM ficam preparadas porque o Graphiti pode precisar delas para extrair entidades e relacoes do texto.

---

## 3. Porque a app nao depende diretamente de `neo4j` e `graphiti`

No `docker-compose.yml`, o servico `app` recebe as env vars do Graphiti, mas nao ficou com `depends_on` para `neo4j` nem para `graphiti`.

Esta decisao foi importante por causa do acceptance criterion:

> Se `GRAPHITI_ENABLED=false`, o sistema funciona sem Neo4j/Graphiti

Se a app dependesse diretamente destes dois containers, o startup podia falhar ou ficar bloqueado mesmo quando o Graphiti estivesse desligado logicamente. Ao manter a app desacoplada:

- o ambiente continua a arrancar
- a configuracao fica disponivel para o codigo
- o client futuro pode decidir em runtime se usa Graphiti ou nao

Isto e a base do graceful disable.

---

## 4. Configuracao Python

### `src/pentest/graphiti/config.py`

Foi criado um pequeno modulo de configuracao:

```python
@dataclass(frozen=True, slots=True)
class GraphitiSettings:
    enabled: bool = False
    url: str = "http://graphiti:8000"
    timeout: float = 30.0
```

### Porque usar uma dataclass

Uma `dataclass` e suficiente para esta story porque:

- a configuracao ainda e pequena
- nao precisamos de validacao pesada
- queremos um objeto simples, imutavel e facil de usar em dependency injection

### Metodo `from_env()`

Este metodo le:

- `GRAPHITI_ENABLED`
- `GRAPHITI_URL`
- `GRAPHITI_TIMEOUT`

e converte esses valores para tipos seguros.

Exemplo:

```python
settings = GraphitiSettings.from_env()
```

Resultado esperado:

- `enabled` e convertido a partir de strings como `true`, `false`, `1`, `0`
- `url` perde a slash final com `rstrip("/")`
- `timeout` passa para `float`

Se `GRAPHITI_TIMEOUT` tiver um valor invalido, cai para `30.0` em vez de rebentar no arranque.

### `_parse_bool()`

Foi criada uma funcao auxiliar para aceitar formatos comuns de env vars:

- truthy: `1`, `true`, `yes`, `on`
- falsy: `0`, `false`, `no`, `off`

Valores desconhecidos usam o default passado, o que torna a configuracao mais tolerante a erro humano.

### `is_disabled`

```python
@property
def is_disabled(self) -> bool:
    return not self.enabled
```

Esta property existe para tornar o codigo futuro mais legivel:

```python
if settings.is_disabled:
    return
```

---

## 5. `.env.example`

Foram promovidas as env vars de Neo4j/Graphiti para configuracao documentada:

```env
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme
GRAPHITI_ENABLED=false
GRAPHITI_URL=http://graphiti:8000
GRAPHITI_TIMEOUT=30
```

### Porque `GRAPHITI_ENABLED=false` no exemplo

No devcontainer optou-se por default interno `true`, para facilitar desenvolvimento local quando os services existem.

No `.env.example`, o valor documentado fica `false` para mostrar que:

- a integracao e opcional
- o sistema deve continuar funcional sem Graphiti
- o modo disabled e um caso legitimo e suportado

---

## 6. Testes

### `tests/unit/test_devcontainer_config.py`

Foram adicionados testes para validar:

- existencia das novas env vars em `.env.example`
- exposicao de `GRAPHITI_ENABLED`, `GRAPHITI_URL`, `GRAPHITI_TIMEOUT` em `devcontainer.json`
- port forwarding de `7474`, `7687`, `8000`
- existencia do servico `neo4j`
- existencia do servico `graphiti`
- env vars do Graphiti no service `app`

Estes testes ajudam a apanhar regressões estruturais sem precisar de subir containers.

### `tests/unit/graphiti/test_config.py`

Foram adicionados testes para tres cenarios:

1. Defaults seguros quando as env vars nao existem
2. Parsing correto quando as env vars estao definidas
3. Fallback seguro quando os valores sao invalidos

Isto cobre diretamente a base do graceful disable pedida pela story.

---

## 7. O que esta pronto depois desta US

Depois da `US-034`, o projeto fica com:

- infraestrutura local para Neo4j + Graphiti
- configuracao documentada
- base de codigo para modo enabled/disabled
- testes unitarios para a configuracao

Isto desbloqueia a `US-035`, onde o proximo passo e criar o `GraphitiClient` propriamente dito.

---

## Related Notes

- [Docs Home](../../README.md)
- [[PROJECT-STRUCTURE]]
- [[DATABASE-SCHEMA]]
- [[US-035-GRAPHITI-CLIENT-EXPLAINED]]
- [[US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED]]

## Limites desta implementacao

Esta story nao faz ainda:

- chamadas HTTP reais ao Graphiti
- verificacao de health no init do client Python
- operacoes `add_messages()` ou search
- integration tests reais contra os containers

Essas pecas pertencem ao `US-035`.
