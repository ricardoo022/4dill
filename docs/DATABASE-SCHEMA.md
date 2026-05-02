---
tags: [database]
---

# LusitAI Database Schema — Referência Completa

Baseado no código real do LusitAI (`src/pentest/database/` + `alembic/versions/001_initial_schema.py`) e na integração Neo4j/Graphiti (`src/pentest/graphiti/`). Documenta o schema **actual implementado**, não o schema completo do PentAGI.

---

## Visão Geral

```
PostgreSQL + pgvector (9 tabelas)
  ├── Workflow (3)         → flows, tasks, subtasks  (hierarquia core)
  ├── Infrastructure (2)  → containers, termlogs
  ├── LLM Interaction (2) → msgchains, toolcalls
  ├── Observability (1)   → msglogs
  └── Vector Memory (1)   → vector_store  (pgvector, 1536-dim)

Neo4j + Graphiti (grafo de conhecimento)
  ├── Nodes               → Entity, Host, Service, Vulnerability, Product, …
  └── Edges               → RELATES_TO (com name + fact)
```

**Total PostgreSQL: 9 tabelas, 10 enums PostgreSQL, 1 índice ivfflat**

### Diferenças face ao PentAGI

| Aspecto | PentAGI | LusitAI |
|---------|---------|---------|
| Auth/multi-tenant | `users`, `roles`, `privileges`, `api_tokens` | Sem auth — single-tenant via MCP |
| Config DB | `providers`, `prompts` (tabelas DB) | Env vars + ficheiros `.md.j2` |
| Prompts inline | Não existe | `flows.prompts` JSON — template resolvido na criação do flow |
| Provider identity | `model_provider_name` + `model_provider_type` (separados) | `model_provider` TEXT (unificado) |
| Vector memory | `vecstorelogs` (audit) | `vector_store` (store real pgvector 1536-dim) |
| Knowledge graph | Não existe | Neo4j via Graphiti |
| Audit logs extras | `agentlogs`, `searchlogs`, `vecstorelogs`, `screenshots` | Fora do scope actual |
| Assistant mode | `assistants`, `assistantlogs` | Fora do scope actual |

---

## Enums PostgreSQL

| Enum | Valores |
|------|---------|
| `flow_status` | `created`, `running`, `waiting`, `finished`, `failed` |
| `task_status` | `created`, `running`, `waiting`, `finished`, `failed` |
| `subtask_status` | `created`, `running`, `waiting`, `finished`, `failed` |
| `container_type` | `primary`, `secondary` |
| `container_status` | `starting`, `running`, `stopped`, `deleted`, `failed` |
| `toolcall_status` | `received`, `running`, `finished`, `failed` |
| `msgchain_type` | `primary_agent`, `reporter`, `generator`, `refiner`, `reflector`, `enricher`, `adviser`, `coder`, `memorist`, `searcher`, `installer`, `pentester`, `summarizer`, `tool_call_fixer` |
| `termlog_type` | `stdin`, `stdout`, `stderr` |
| `msglog_type` | `thoughts`, `browser`, `terminal`, `file`, `search`, `advice`, `input`, `done`, `answer`, `report` |
| `msglog_result_format` | `terminal`, `plain`, `markdown` |

Todos criados idempotentes (`IF NOT EXISTS`) na migração `001_initial_schema`. O SQLAlchemy usa `create_type=False` + `values_callable` para serialização lowercase correcta.

---

## Workflow Tables

### `flows`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `status` | `flow_status` (default `created`) | Ciclo de vida do scan |
| `title` | TEXT | Gerado pelo LLM; default `untitled` |
| `model` | TEXT | Modelo LLM usado neste scan |
| `model_provider` | TEXT | Nome do provider configurado |
| `language` | TEXT | Idioma detectado do input (`en`, `pt`, …) |
| `functions` | JSON (default `{}`) | Tool definitions customizadas |
| `prompts` | JSON | **Templates de prompt resolvidos na criação** — guarda os system prompts de cada agente para que o scan inteiro use a mesma versão, mesmo que os ficheiros `.md.j2` mudem a meio |
| `tool_call_id_template` | TEXT | Pattern para gerar IDs de tool calls (ex: `toulu_{r:24:b}` para Claude) |
| `trace_id` | TEXT nullable | OpenTelemetry trace ID |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger `tr_flows_updated_at` |
| `deleted_at` | TIMESTAMPTZ nullable | Soft delete |

**Índices:** `ix_flows_status`, `ix_flows_title`

**Relações (cascade delete):** tasks → subtasks → toolcalls, containers → termlogs, msgchains, msglogs

> `prompts` é a principal diferença face ao PentAGI: em vez de guardar overrides por user na tabela `prompts`, o LusitAI resolve os templates Jinja2 uma vez na criação do flow e guarda o resultado em JSON. Garante consistência durante todo o scan.

---

### `tasks`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `status` | `task_status` | Ciclo de vida |
| `title` | TEXT | Gerado pelo LLM |
| `input` | TEXT | Pedido original do utilizador (via MCP) |
| `result` | TEXT (default `''`) | Relatório final do Reporter |
| `flow_id` | FK → flows CASCADE | Parent scan |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger |

**Índices:** `ix_tasks_status`, `ix_tasks_title`, `ix_tasks_flow_id`

**Porquê existe:** Um task por invocação MCP dentro de um flow. O Generator decompõe o `input` em subtasks. Quando todas completam, o Reporter escreve o `result`.

---

### `subtasks`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `status` | `subtask_status` | Ciclo de vida |
| `title` | TEXT | Criado pelo Generator |
| `description` | TEXT | Instrução detalhada para o Orchestrator |
| `context` | TEXT (default `''`) | Contexto adicional injectado pelo Refiner |
| `result` | TEXT (default `''`) | Output do Orchestrator via tool `done` |
| `task_id` | FK → tasks CASCADE | Parent task |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger |

**Índices:** `ix_subtasks_status`, `ix_subtasks_title`, `ix_subtasks_task_id`

**Porquê existe:** Unidade atómica de execução. O Orchestrator executa uma subtask de cada vez. O Refiner pode adicionar/remover/modificar subtasks mid-scan.

---

## Infrastructure Tables

### `containers`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `type` | `container_type` (default `primary`) | `primary` = sandbox Kali principal; `secondary` = spawned por agentes |
| `name` | TEXT | Nome do container (MD5 de UUID4 por default) |
| `image` | TEXT | Imagem Docker (`kalilinux/kali-rolling`) |
| `status` | `container_status` (default `starting`) | Ciclo de vida |
| `local_id` | TEXT UNIQUE nullable | Docker container ID (de `docker create`) |
| `local_dir` | TEXT nullable | Directório montado no host para partilha de ficheiros |
| `flow_id` | FK → flows CASCADE | Pertence a este scan |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger |

**Índices:** `ix_containers_type`, `ix_containers_name`, `ix_containers_status`, `ix_containers_flow_id`

**Porquê existe:** Tracking para crash recovery — se o servidor crashar, sabe quais containers Kali limpar ao reiniciar.

---

### `termlogs`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `type` | `termlog_type` | `stdin`, `stdout`, ou `stderr` |
| `text` | TEXT | Output real do terminal |
| `container_id` | FK → containers CASCADE | Qual container |
| `flow_id` | FK → flows CASCADE | Parent flow |
| `task_id` | FK → tasks CASCADE nullable | Parent task (se aplicável) |
| `subtask_id` | FK → subtasks CASCADE nullable | Parent subtask (se aplicável) |
| `created_at` | TIMESTAMPTZ | Auditoria |

**Índices:** `ix_termlogs_type`, `ix_termlogs_container_id`, `ix_termlogs_flow_id`, `ix_termlogs_task_id`, `ix_termlogs_subtask_id`

**Porquê existe:** Audit trail completo de cada comando executado no sandbox. Driver: debugging, observabilidade e crash recovery.

---

## LLM Interaction Tables

### `msgchains`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `type` | `msgchain_type` (default `primary_agent`) | Qual agente é dono desta chain |
| `model` | TEXT | Modelo LLM usado |
| `model_provider` | TEXT | Nome do provider |
| `usage_in` | BIGINT (default 0) | Tokens de input consumidos |
| `usage_out` | BIGINT (default 0) | Tokens de output consumidos |
| `usage_cache_in` | BIGINT (default 0) | Tokens de prompt cache lidos (Claude) |
| `usage_cache_out` | BIGINT (default 0) | Tokens de prompt cache escritos |
| `usage_cost_in` | FLOAT (default 0.0) | Custo $ do input |
| `usage_cost_out` | FLOAT (default 0.0) | Custo $ do output |
| `duration_seconds` | FLOAT (default 0.0) | Tempo de execução wall-clock |
| `chain` | JSON (default `[]`) | **Histórico interno de execução** — array de mensagens LangChain (HumanMessage, AIMessage, ToolMessage, …) |
| `flow_id` | FK → flows CASCADE | Parent flow |
| `task_id` | FK → tasks CASCADE nullable | Task associado |
| `subtask_id` | FK → subtasks CASCADE nullable | Subtask associada |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger |

**Índices:** `ix_msgchains_type`, `ix_msgchains_flow_id`, `ix_msgchains_task_id`, `ix_msgchains_subtask_id`, `ix_msgchains_created_at`, `ix_msgchains_model_provider`, `ix_msgchains_model`, `ix_msgchains_type_flow_id`, `ix_msgchains_created_at_flow_id`, `ix_msgchains_type_created_at`, `ix_msgchains_type_task_id_subtask_id`

**Porquê existe:** Core do sistema de agentes. Cada invocação do LangGraph cria uma msgchain. O campo `chain` (JSON) contém o histórico interno incluindo tool calls e respostas. Usado para:
- **Recovery**: recarregar chain e continuar após crash
- **Summarization**: comprimir mensagens quando a chain fica grande
- **Cost tracking**: custo exacto por agente
- **Debugging**: replay de qualquer conversa de agente

---

### `toolcalls`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `call_id` | TEXT | ID gerado pelo LLM no pattern do provider |
| `status` | `toolcall_status` (default `received`) | Ciclo de vida da execução |
| `name` | TEXT | Nome da tool (`terminal`, `pentester`, `done`, …) |
| `args` | JSON (default `{}`) | Argumentos que o LLM forneceu |
| `result` | TEXT (default `''`) | Output da execução |
| `duration_seconds` | FLOAT (default 0.0) | Tempo de execução |
| `flow_id` | FK → flows CASCADE | Parent flow |
| `task_id` | FK → tasks CASCADE nullable | Task associado |
| `subtask_id` | FK → subtasks CASCADE nullable | Subtask associada |
| `created_at` | TIMESTAMPTZ | Auditoria |
| `updated_at` | TIMESTAMPTZ | Auto-update via trigger |

**Índices:** `ix_toolcalls_call_id`, `ix_toolcalls_status`, `ix_toolcalls_name`, `ix_toolcalls_flow_id`, `ix_toolcalls_task_id`, `ix_toolcalls_subtask_id`, `ix_toolcalls_created_at`, `ix_toolcalls_updated_at`, `ix_toolcalls_flow_id_status`, `ix_toolcalls_name_status`, `ix_toolcalls_name_flow_id`, `ix_toolcalls_status_updated_at`

**Porquê existe:** Cada tool call tracked individualmente para:
- **Loop detection**: mesma tool chamada 5+ vezes → abort
- **Adviser trigger**: 20+ calls → Adviser intervém
- **Audit**: que comandos foram executados, com que args, e resultado

---

## Observability Table

### `msglogs`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `type` | `msglog_type` | Categoria do evento |
| `message` | TEXT | Log legível |
| `result` | TEXT (default `''`) | Output associado ao evento |
| `result_format` | `msglog_result_format` (default `plain`) | Como renderizar o resultado: `plain`, `markdown`, `terminal` |
| `flow_id` | FK → flows CASCADE | Parent flow |
| `task_id` | FK → tasks CASCADE nullable | Task associado |
| `subtask_id` | FK → subtasks CASCADE nullable | Subtask associada |
| `created_at` | TIMESTAMPTZ | Auditoria |

**Tipos de msglog:** `thoughts` (raciocínio do agente), `browser` (acesso web), `terminal` (comando executado), `file` (operação de ficheiro), `search` (pesquisa web), `advice` (intervenção do Adviser), `input` (pedido do user), `done` (subtask concluída), `answer` (resposta do agente), `report` (relatório final)

**Índices:** `ix_msglogs_type`, `ix_msglogs_flow_id`, `ix_msglogs_task_id`, `ix_msglogs_subtask_id`, `ix_msglogs_result_format`

**Porquê existe:** Registo de eventos operacionais legíveis do engine. Diferente de `msgchains` (histórico LLM raw/interno) — `msglogs` são eventos curados para observabilidade e debugging.

---

## Vector Memory Table

### `vector_store`

| Coluna | Tipo | Porquê |
|--------|------|--------|
| `id` | BIGINT PK | Referência interna |
| `content` | TEXT | Texto completo do documento/chunk armazenado |
| `metadata_` | JSON (default `{}`) | Metadata estruturada: `flow_id`, `task_id`, `doc_type`, etc. |
| `embedding` | `vector(1536)` | Embedding semântico (OpenAI text-embedding-3-small ou equivalente) |
| `created_at` | TIMESTAMPTZ | Auditoria |

**Índices:**
- `ix_vector_store_embedding_ivfflat` — ivfflat index com `vector_cosine_ops` (similaridade cosine)
- `ix_vector_store_metadata_flow_id` — expressão `(metadata_->>'flow_id')` para filtrar por scan
- `ix_vector_store_metadata_task_id` — expressão `(metadata_->>'task_id')` para filtrar por task
- `ix_vector_store_metadata_doc_type` — expressão `(metadata_->>'doc_type')` para filtrar por tipo de documento

**Porquê existe:** Memória semântica de longo prazo do Memorist. Guarda achados, contexto de subtasks, e documentos do scan para pesquisa por similaridade. O ivfflat index torna a pesquisa cosine escalável com grandes volumes de embeddings. O índice de expressão no `metadata_` JSON permite filtrar por scan sem varrer toda a tabela.

> **Diferença face ao PentAGI:** O PentAGI usa `vecstorelogs` como audit trail de operações de memória (quem pesquisou o quê). O LusitAI implementa o store real com pgvector directamente nesta tabela; o audit fica nos `msglogs` com `type='search'`.

---

## Triggers e Funções PostgreSQL

```sql
-- Função reutilizada por todos os triggers de updated_at
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';
```

**Triggers `BEFORE UPDATE`** activos em: `flows`, `tasks`, `subtasks`, `containers`, `toolcalls`, `msgchains`

Padrão de naming: `tr_{table_name}_updated_at`

---

## Foreign Keys & Cascade Behavior

Todas as foreign keys usam `ON DELETE CASCADE`:

```
Apagar flow     → cascata para: tasks, containers, toolcalls, msgchains, msglogs, termlogs
Apagar task     → cascata para: subtasks, toolcalls, msgchains, msglogs, termlogs
Apagar subtask  → cascata para: toolcalls, msgchains, msglogs, termlogs
Apagar container → cascata para: termlogs desse container
```

`vector_store` não tem FK — isolamento por `metadata_->>'flow_id'` em vez de FK.

---

## Neo4j Knowledge Graph (Graphiti)

O grafo de conhecimento vive no Neo4j e é gerido via serviço Graphiti (REST API em `http://graphiti:8000`). Não tem migração Alembic — o schema Neo4j é criado dinamicamente pela Graphiti e pelo `LocalGraphitiFallback`.

### Isolamento por `group_id`

Cada nó e edge tem `group_id` (string). No LusitAI, o `group_id` corresponde ao scan ou ao flow. Queries filtram sempre por `group_id IN $group_ids` para isolar dados entre scans.

### Node Labels

Todos os nós têm o label base `:Entity`. Os nós específicos têm dois labels: `:Entity:<SpecificLabel>`.

| Label | O que representa | Extraído de |
|-------|-----------------|-------------|
| `Entity` | Base (todos os nós) | — |
| `Host` | Hostnames, IPs, domínios | Regex de hostnames/IPs no output dos agentes |
| `Service` | Serviços em portos (ex: `ssh:22`, `http:80`) | Detecção de portos + hints de serviço |
| `Vulnerability` | CVEs (`CVE-2024-XXXXX`) | Regex CVE no output |
| `Product` | Software com versão (nginx, OpenSSH, MySQL, …) | Patterns de produto com versão opcional |
| `OperatingSystem` | SO detectado (ex: `Linux 5.15`) | Pattern `Linux` com versão |
| `Credential` | Pares username/password (`user/pass`) | Regex de credenciais formato `x/y` |
| `Endpoint` | URL paths (`/api/v1/users`) | Regex de paths |
| `Domain` | Subdomínios | Inferido de contexto `subdomain_of` |

### Node Properties

| Propriedade | Tipo | Porquê |
|-------------|------|--------|
| `uuid` | String | Identificador único do nó |
| `name` | String | Nome/identificador da entidade (ex: `192.168.1.1`, `CVE-2024-1234`) |
| `label` | String | Label específico do nó |
| `summary` | String | Frase/contexto de onde a entidade foi extraída (max 500 chars) |
| `group_id` | String | Identificador do scan — isola dados entre scans |
| `created_at` | DateTime | Criado via `coalesce(n.created_at, datetime())` — idempotente |

### Edge Types

| Tipo | Quando se cria |
|------|---------------|
| `RELATES_TO` | Única relação genérica — todos os edges usam este tipo. O campo `name` especifica a semântica. |

### Edge Properties

| Propriedade | Tipo | Porquê |
|-------------|------|--------|
| `uuid` | String | Identificador único da relação |
| `group_id` | String | Isolamento por scan |
| `name` | String | Tipo de relação semântica (ver tabela abaixo) |
| `fact` | String | Frase original que originou esta relação |
| `created_at` | DateTime | Criado idempotente via `coalesce` |

### Relações Semânticas (`RELATES_TO.name`)

| name | Semântica |
|------|-----------|
| `exposes` | Host expõe um serviço (`host → service`) |
| `runs` | Host executa um produto/OS (`host → product`) |
| `uses` | Host usa uma tecnologia (`host → product`, em contexto de stack/backend) |
| `has_vulnerability` | Entidade tem uma vulnerabilidade (`host/product → CVE`) |
| `has_credential` | Host tem credencial detectada (`host → credential`) |
| `communicates_with` | Dois hosts comunicam entre si |
| `related_to` | Relação genérica entre dois hosts |
| `resolves_to` | Hostname resolve para IP |
| `subdomain_of` | Subdomínio pertence a domínio raiz |

### Queries Cypher Típicas

```cypher
-- Buscar todos os nós de um scan
MATCH (n:Entity)
WHERE n.group_id IN ['scan-abc123']
RETURN n.uuid, n.name, labels(n), n.summary

-- Buscar todas as relações de um scan
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.group_id IN ['scan-abc123']
RETURN r.uuid, r.name, r.fact, a.name AS source, b.name AS target

-- Buscar vulnerabilidades encontradas
MATCH (vuln:Entity:Vulnerability)
WHERE vuln.group_id IN ['scan-abc123']
RETURN vuln.name, vuln.summary

-- Buscar serviços de um host específico
MATCH (h:Entity:Host {name: '192.168.1.10'})-[r:RELATES_TO]->(s:Entity:Service)
WHERE r.group_id IN ['scan-abc123'] AND r.name = 'exposes'
RETURN s.name, r.fact
```

### Modo de Fallback Local (`LocalGraphitiFallback`)

Quando o serviço Graphiti não materializa episodes correctamente (limitação conhecida de algumas builds), o `LocalGraphitiFallback` escreve directamente no Neo4j via Bolt (`neo4j` Python driver). Activado via `GRAPHITI_LOCAL_FALLBACK_ENABLED=true`.

O fallback usa as mesmas queries Cypher com `MERGE` idempotente — não cria duplicados se o nó/edge já existir.

---

## Configuração por Ambiente

### PostgreSQL (env vars)

| Variável | Valor (devcontainer) |
|----------|---------------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/lusitaidb` |

### Neo4j + Graphiti (env vars)

| Variável | Valor (devcontainer) | Uso |
|----------|---------------------|-----|
| `GRAPHITI_ENABLED` | `true` | Activar integração Graphiti |
| `GRAPHITI_URL` | `http://graphiti:8000` | URL da API Graphiti |
| `GRAPHITI_TIMEOUT` | `30` | Timeout em segundos |
| `NEO4J_URI` | `bolt://neo4j:7687` | Bolt directo (fallback + queries) |
| `NEO4J_USER` | `neo4j` | Credenciais Neo4j |
| `NEO4J_PASSWORD` | `changeme` | Credenciais Neo4j |
| `GRAPHITI_LOCAL_FALLBACK_ENABLED` | `false` | Fallback directo para Neo4j |

---

## Related Notes

- [[US-011-ALEMBIC-MIGRATIONS-EXPLAINED]] — Alembic async env, design da migração inicial, ivfflat index
- [[US-008-CORE-DB-MODELS]] — SQLAlchemy 2.0 models, cascade delete, soft-delete, indexes
- [[US-007-DATABASE-ENUM-TYPES]] — PostgreSQL enum types + SQLAlchemy wrappers
- [[US-035-GRAPHITI-CLIENT-EXPLAINED]] — Graphiti async HTTP client, search methods, fallback
- [[US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED]] — LangChain tool para pesquisa Graphiti
