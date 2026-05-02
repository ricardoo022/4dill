---
tags: [architecture]
---

# PentestAI — Project Structure

Tradução direta do PentAGI (Go) para Python. Mesmas pastas, mesma lógica.

---

## Stack Técnica

| Componente | PentAGI (Go) | SecureDev (Python) | Porquê |
|---|---|---|---|
| Linguagem | Go | **Python** | Equipa conhece, ecossistema AI |
| LLM SDK | langchaingo (fork próprio) | **LangChain Python** | Equivalente direto, multi-provider |
| API | REST + GraphQL (Gin + gqlgen) | **MCP Server** | Outro sistema liga-se como MCP Client |
| DB ORM | SQLC + GORM | **SQLAlchemy 2.0 async** | Standard Python, Alembic migrations |
| Database | PostgreSQL + pgvector | **PostgreSQL + pgvector** | State + embeddings |
| Knowledge Graph | Neo4j + Graphiti (opcional) | **Neo4j + Graphiti** | Relações entre entidades descobertas no scan |
| Docker SDK | docker/docker (Go SDK) | **docker-py** | Equivalente em Python |
| Container | vxcontrol/kali-linux | **Kali Linux** | Ferramentas de segurança pré-instaladas |
| Prompts | Go text/template (.tmpl) | **Jinja2 + .md** | Equivalente em Python |
| Dev setup | Docker Compose | **VS Code Dev Container** | Equipa toda com mesmo ambiente |

---

## Directory Structure

```
securedev-pentest/
│
├── .devcontainer/          # VS Code Dev Container config
│
├── src/pentest/
│   ├── controller/
│   ├── providers/
│   ├── tools/
│   ├── docker/
│   ├── database/
│   ├── graphiti/
│   ├── templates/
│   ├── agents/
│   ├── mcp/
│   ├── models/
│   └── recon/
│
├── tests/
│
└── docker/
```

---

## controller/

**O quê:** A orquestração do scan. Decide O QUÊ corre e EM QUE ORDEM.

**Porquê existe:** Alguém tem de gerir o ciclo de vida de um scan — desde que o user pede até ao report final. O controller é esse gestor. Não executa testes, não chama LLMs, não toca em Docker. Só coordena.

**Como funciona no PentAGI:** `pkg/controller/` com 4 ficheiros (flow.go, task.go, subtask.go, subtasks.go).

**O fluxo que implementa:**

```
User pede scan de https://app.example.com
    │
    ▼
flow.py  →  "Crio um container Docker para este scan.
              Crio um Task com o pedido do user.
              Fico à espera que o Task acabe."
    │
    ▼
task.py  →  "Chamo o Generator para criar uma lista de subtasks.
             Para cada subtask:
               1. Passo ao SubtaskWorker para executar
               2. Chamo o Refiner para ajustar o plano
             Quando acabam todas, chamo o Reporter para o resultado final."
    │
    ▼
subtask.py  →  "Recebo uma subtask (ex: 'testar RLS nas tabelas').
                Chamo perform_agent_chain() do providers/ para executar.
                Retorno: sucesso, falha, ou a aguardar input do user."
    │
    ▼
subtasks.py  →  "Giro a lista de subtasks.
                 generate_subtasks() chama o Generator agent.
                 refine_subtasks() chama o Refiner agent.
                 pop_subtask() devolve a próxima por executar."
```

**Equivalente PentAGI:**
- `flow.py` = `pkg/controller/flow.go` (FlowWorker)
- `task.py` = `pkg/controller/task.go` (TaskWorker)
- `subtask.py` = `pkg/controller/subtask.go` (SubtaskWorker)
- `subtasks.py` = `pkg/controller/subtasks.go` (SubtaskController)

---

## providers/

**O quê:** O motor de execução dos agentes. Chama o LLM, recebe tool calls, executa-as, e repete.

**Porquê existe:** Quando o controller diz "executa esta subtask", alguém tem de realmente chamar o Claude, interpretar a resposta, executar as tools que o Claude pediu, e repetir até o agente dizer "done". O providers/ faz isso.

**Como funciona no PentAGI:** `pkg/providers/` com performer.go (o loop), provider.go (interface LLM), e subpastas por provider (anthropic/, openai/, etc).

**O loop central que implementa (`perform_agent_chain`):**

```
Recebe: mensagens + tools disponíveis do agente
    │
    ▼
Chama LLM (via LangChain) com as mensagens e tools
    │
    ▼
LLM responde com tool_calls? ─── NÃO ──→ Chama Reflector
    │                                       (corrige, max 3x)
   SIM
    │
    ▼
Para cada tool_call:
    ├── É "done" ou "ask"? → PARA (subtask completa ou aguarda input)
    ├── É "scanner"/"coder"/etc? → Cria NOVO perform_agent_chain para esse agente
    ├── É "terminal"? → Executa comando no Docker
    └── É "google"/"browser"/etc? → Faz pesquisa
    │
    ▼
Agente repetiu a mesma tool 5+ vezes? → ABORTA
Agente já fez 20+ tool calls? → Chama Adviser/Mentor
Contexto ficou grande demais? → Chama Summarizer
    │
    ▼
Volta ao início (chama LLM outra vez com os novos resultados)
```

**Também inclui:**
- Chamadas ao LLM via LangChain (Claude, e futuramente outros providers)
- Reflector: corrige agentes que devolvem texto em vez de tool calls
- Summarizer: comprime message chains quando ficam grandes
- Monitor: detecta loops (20+ calls) e repetições (5+ mesma tool)

**Equivalente PentAGI:**
- `perform_agent_chain()` = `pkg/providers/performer.go` → `performAgentChain()`
- Provider LLM = `pkg/providers/anthropic/`, `openai/`, etc.
- Reflector = dentro de `performer.go` → `performReflector()`
- Summarizer = `pkg/csum/` (chain summarization)

---

## tools/

**O quê:** O sistema de tools. Define quais tools existem, o que cada uma faz, e executa-as quando o LLM pede.

**Porquê existe:** Quando o Claude responde com `tool_call: terminal("nmap -sV target.com")`, alguém tem de: (1) saber que a tool "terminal" existe, (2) saber os seus parâmetros, (3) executá-la no sítio certo, (4) devolver o resultado. O tools/ faz isto.

**Como funciona no PentAGI:** `pkg/tools/` com registry.go (definições), executor.go (execução), e ficheiros por tool.

**O que contém:**
- **Registry:** Dicionário com todas as tools (nome, descrição, parâmetros JSON schema, tipo). Cada agente recebe um subconjunto conforme o seu config.
- **Executor:** Recebe um tool_call, encontra o handler correto no registry, executa, devolve resultado. Faz retry (max 3x) se os argumentos estão mal.
- **Handlers:** Um por tipo de tool:
  - `terminal` → executa comando no Docker container (passa pelo filtro primeiro)
  - `file` → lê/escreve ficheiros no container
  - `browser` → scraping de páginas web
  - `search` → Google, DuckDuckGo, Tavily, Sploitus
  - `memory` → operações no vector DB (search/store)
  - `barriers` → done, ask, hack_result, code_result, etc. (param o loop)
  - `filter` → bloqueia comandos destrutivos antes de executar no terminal

**Os 7 tipos de tools (do PentAGI):**
1. **Environment** (terminal, file) → executam no Docker
2. **Search Network** (google, duckduckgo, tavily, browser) → pesquisam na web
3. **Search Vector DB** (search_in_memory, search_guide) → pesquisam na memória
4. **Agent** (scanner, coder, searcher, memorist, adviser) → delegação para outro agente
5. **Store Agent Result** (hack_result, code_result, search_result) → guardam output
6. **Store Vector DB** (store_guide, store_answer, store_code) → guardam na memória
7. **Barrier** (done, ask) → param a execução do loop

**Equivalente PentAGI:**
- Registry = `pkg/tools/registry.go`
- Executor = `pkg/tools/executor.go`
- Terminal = `pkg/tools/terminal.go`
- Search = `pkg/tools/google.go`, `duckduckgo.go`, `tavily.go`, etc.
- Memory = `pkg/tools/memory.go`, `guide.go`
- Browser = `pkg/tools/browser.go`

---

## docker/

**O quê:** Gestão de containers Docker. Cria, executa comandos dentro, e destrói containers isolados.

**Porquê existe:** Os agentes precisam de correr ferramentas de segurança (nmap, nuclei, sqlmap) num ambiente isolado. O docker/ gere esse sandbox — cada scan tem o seu container, com o seu volume, os seus ports, e é destruído no final.

**Como funciona no PentAGI:** `pkg/docker/client.go` — um único ficheiro com o Docker client.

**O que faz:**
- **Create:** Puxa imagem (Kali Linux), cria container com volume isolado `/work/scan-{id}`, aloca 2 ports
- **Exec:** Quando o tools/terminal.py precisa de correr `nmap`, chama docker exec dentro do container
- **Copy:** Transfere ficheiros entre o host e o container
- **Destroy:** Quando o scan acaba, para e remove o container + volume
- **Cleanup:** No startup, limpa containers órfãos de scans anteriores que crasharam
- **Fallback:** Se a imagem pedida falha ao descarregar, usa debian:latest

**Equivalente PentAGI:** `pkg/docker/client.go`

---

## database/

**O quê:** Persistência. Guarda o estado de tudo — flows, tasks, subtasks, conversas dos agentes, logs de terminal, tool calls.

**Porquê existe:** Se o servidor crashar, precisamos de saber em que ponto estava o scan. Se queremos ver o historial de um scan, está na DB. Se o Memorist quer pesquisar scans anteriores, pesquisa aqui. Usa SQLAlchemy 2.0 async + Alembic para migrations.

**Como funciona no PentAGI:** `pkg/database/` com queries geradas por SQLC + GORM para operações complexas.

**Tabelas core:**
- `flows` → sessão de scan (status, target URL, model)
- `tasks` → pedido dentro de um flow (input, result)
- `subtasks` → passo atómico (title, description, result)
- `msg_chains` → histórico de conversação por agente (JSON com todas as messages)
- `tool_calls` → log de cada tool call (nome, args, resultado)
- `term_logs` → output do terminal (stdin/stdout/stderr)
- `containers` → Docker containers por flow (image, docker ID, status)
- `vector_store` → memória de longo prazo com embeddings (pgvector)

**Equivalente PentAGI:**
- Schema = `backend/migrations/sql/`
- Queries = `backend/sqlc/models/`
- DB connection = `pkg/database/`

---

## graphiti/

**O quê:** Cliente para o Graphiti API + Neo4j. Knowledge graph que guarda relações entre entidades descobertas no scan.

**Porquê existe:** O pgvector guarda embeddings (pesquisa semântica por similaridade). Mas não sabe relações. Quando o Scanner descobre que `porta 443 → nginx 1.24 → CVE-2024-7890`, o pgvector guarda cada facto separado. O Graphiti/Neo4j guarda o GRAFO de relações — e permite perguntar "que vulnerabilidades estão ligadas ao nginx nesta porta?".

**Como funciona no PentAGI:** `pkg/graphiti/` — cliente HTTP para o Graphiti API. O Graphiti é um serviço separado (Docker) que fala com o Neo4j.

**O que faz:**
- **Guardar:** Quando um agente produz output (nmap result, RLS test, CVE lookup), o texto é enviado ao Graphiti que extrai entidades e relações automaticamente usando LLM
- **Pesquisar:** Agentes podem pesquisar o knowledge graph em linguagem natural (`graphiti_search("vulnerabilities on port 443")`)
- **Relações temporais:** Sabe QUANDO cada facto foi descoberto — se info muda durante o scan, resolve conflitos

**Arquitectura:**

```
Agent → graphiti_search("...")
    │
    ▼
graphiti/ (nosso cliente Python)
    │
    ▼
Graphiti API (serviço Docker, port 8000)
    ├── Usa LLM para extrair entidades do texto
    ├── Usa LLM para traduzir queries em Cypher
    │
    ▼
Neo4j (graph database Docker, port 7687)
    └── Guarda e consulta o grafo
```

**Diferença vs pgvector:**

| | pgvector | Neo4j/Graphiti |
|---|---|---|
| Pergunta | "encontra coisas semelhantes a X" | "que relações existem entre X e Y?" |
| Guarda | Embeddings (vectores numéricos) | Entidades + relações (grafo) |
| Exemplo | "outputs sobre RLS" → retorna textos semelhantes | "users table → RLS disabled → 150 PII records → GDPR" |

**Equivalente PentAGI:** `pkg/graphiti/` (cliente) + `docker-compose-graphiti.yml` (Neo4j + Graphiti services)

---

## templates/

**O quê:** Prompt templates. Um ficheiro .md por agente, com variáveis Jinja2 que são preenchidas em runtime.

**Porquê existe:** Cada agente precisa de um system prompt diferente. O Scanner precisa de saber que ferramentas existem no container. O Generator precisa de saber as FASE 0-21. O Reporter precisa de saber o Pydantic schema. Os templates definem o "cérebro" de cada agente.

**Como funciona no PentAGI:** `pkg/templates/prompts/*.tmpl` — Go templates com variáveis ({{.ExecutionContext}}, {{.ToolPlaceholder}}, etc). Nós usamos Jinja2 com ficheiros .md.

**O que contém:**
- Um template por agente (orchestrator.md, scanner.md, coder.md, etc.)
- Template do execution context (resumo do scan injetado em todos os agentes)
- Conhecimento das FASE 0-21 (injetado no Generator e Scanner)
- Variáveis renderizadas em runtime: tool names, execution context, current time, language

**Equivalente PentAGI:** `pkg/templates/prompts/*.tmpl` + `pkg/templates/templates.go` (renderer)

---

## agents/

**O quê:** Configuração dos 10 agentes. Define QUAIS tools cada agente tem, para QUEM pode delegar, qual o LIMITE de iterações, e qual TEMPLATE de prompt usa.

**Porquê existe:** No PentAGI isto está espalhado pelo código (hardcoded em performer.go e nos executors). Nós centralizamos num sítio para ser fácil de manter e perceber.

**NÃO existe no PentAGI como pasta separada.** É a única adição nossa.

**O que contém:**
- Config base (que campos um agente tem: prompt, tools, limites, barrier)
- Config de cada agente (Orchestrator tem terminal+file+todos os agents, Scanner tem terminal+file+browser, Searcher só tem browser+search, etc.)

**Os 12 agentes:**
1. **Generator** — planeia o scan, cria ≤15 subtasks
2. **Orchestrator** — coordena, delega para especialistas
3. **Scanner** — corre os testes de segurança
4. **Coder** — escreve scripts custom
5. **Searcher** — pesquisa web (CVEs, técnicas)
6. **Memorist** — memória de longo prazo
7. **Adviser** — orientação + mentor (intervém em loops)
8. **Installer** — instala/configura ferramentas no container em runtime
9. **Enricher** — adiciona contexto antes do Adviser responder (pipeline dois passos)
10. **Refiner** — ajusta plano mid-scan
11. **Reflector** — corrige agentes que não usam tools
12. **Reporter** — Judge Mode + JSON final

---

## mcp/

**O quê:** MCP Server. O ponto de entrada do sistema — o outro sistema liga-se aqui como MCP Client.

**Porquê existe:** O PentestAI não tem frontend próprio. Vai ser ligado a outro sistema via MCP (Model Context Protocol). O mcp/ expõe tools e resources que o outro sistema chama.

**O que o PentAGI tem em vez disto:** `pkg/server/` (REST API com Gin) + `pkg/graph/` (GraphQL + WebSocket subscriptions). Nós substituímos por MCP.

**Tools expostas via MCP:**

```
start_scan(url, token)        → Inicia scan (cria flow + task)
get_scan_status(scan_id)      → Estado do scan (running, finished, failed)
get_scan_report(scan_id)      → JSON final (ScanReport Pydantic)
stop_scan(scan_id)            → Parar scan
list_scans()                  → Listar scans activos e histórico
```

**Resources expostas via MCP:**

```
scan_logs(scan_id)            → Terminal logs em tempo real
scan_findings(scan_id)        → Findings parciais (mid-scan)
scan_subtasks(scan_id)        → Progresso das subtasks
```

---

## models/

**O quê:** Pydantic models. Tipos de dados partilhados por todo o sistema.

**Porquê existe:** Em Go, os tipos estão definidos inline em cada package. Em Python, centralizamos os modelos para evitar imports circulares e ter um sítio único para os tipos de dados.

**Parte já existe:** `app/models/scan_output.py` e `app/models/enums.py` (o output final do scan).

**O que contém:**
- Output do scan (ScanReport, Finding, Target, Stack) — já existe
- Enums (Severity, Category, FindingType) — já existe
- Tipos de agentes (AgentType, AgentConfig)
- Tipos de tools (ToolCall, ToolResponse, ToolType, ToolDefinition)
- Tipos de estado (FlowState, TaskState, SubtaskState, MsgChain)

**Equivalente PentAGI:** Não tem pasta dedicada — types estão espalhados por cada package Go.

---

## recon/

**O quê:** Backend detection engine (FASE 0). Identifica o tipo de backend do alvo antes dos agentes entrarem em ação.

**Porquê existe:** Módulo novo, sem equivalente no PentAGI. O SecureDev precisa de saber se o alvo usa Supabase, Firebase, ou API customizada para decidir que fases do scan executar. Corre antes do Generator agent.

**O que contém:**
- `supabase.py` — detecção de Supabase (URL, anon key, verificação /rest/v1/)
- `firebase.py` — detecção de Firebase (firebaseConfig, initializeApp)
- `custom_api.py` — detecção de frameworks (Next.js, SvelteKit, Express, Django, etc.) + GraphQL
- `subdomains.py` — descoberta de subdomínios (prefixos comuns, SSL SANs, links HTML)
- `orchestrator.py` — combina tudo: subdomain discovery → detectors → BackendProfile com scan_path

**Equivalente PentAGI:** Não existe — funcionalidade exclusiva do SecureDev, baseada na FASE 0 de `lusitai-internal-scan/`.

---

## tests/

**O quê:** Testes automatizados.

- `unit/` — testes isolados com mocks (mock LLM, mock Docker)
- `integration/` — testes com DB e Docker reais
- `e2e/` — scan completo contra target de teste

---

## docker/

**O quê:** Ficheiros Docker para build e desenvolvimento.

- Dockerfile do serviço PentestAI
- docker-compose para o PostgreSQL + pgvector em dev
- Dockerfile da imagem Kali customizada (se necessário)

---

## .devcontainer/

**O quê:** VS Code Dev Container. Qualquer developer que abra o projeto no VS Code tem automaticamente:

- Python com a versão correcta
- PostgreSQL + pgvector a correr
- Docker-in-Docker (para os containers de scan)
- Todas as dependências instaladas
- Mesmas extensões VS Code para toda a equipa

---

## Mapping PentAGI → SecureDev

| PentAGI (`backend/pkg/`) | SecureDev (`src/pentest/`) | Tecnologia |
|---|---|---|
| `controller/` | `controller/` | Python async |
| `providers/` | `providers/` | LangChain Python |
| `tools/` | `tools/` | Python handlers |
| `docker/` | `docker/` | docker-py SDK |
| `database/` | `database/` | SQLAlchemy 2.0 async + Alembic |
| `templates/prompts/` | `templates/` | Jinja2 + .md |
| `server/` + `graph/` | `mcp/` | MCP Server (substitui REST+GraphQL) |
| — | `agents/` | Novo (configs centralizadas) |
| — | `models/` | Pydantic v2 |
| — | `.devcontainer/` | VS Code Dev Container |

---

## Related Notes

- [Docs Home](README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[DATABASE-SCHEMA]]
- [[USER-STORIES]]
