---
tags: [home]
---

# Documentação — LusitAI AI Pentest

Documentação de arquitectura, implementação e planning do projecto.

> Navegar no Obsidian: abrir este ficheiro → Ctrl+G para graph view.

---

## Arquitectura

| Doc | Descrição |
|---|---|
| [AGENT-ARCHITECTURE](AGENT-ARCHITECTURE.md) | Os 12 agentes, ferramentas, delegação, memória |
| [EXECUTION-FLOW](EXECUTION-FLOW.md) | Fluxo completo (7 fases, estado DB em cada passo) |
| [PROJECT-STRUCTURE](PROJECT-STRUCTURE.md) | Mapeamento PentAGI Go → Python, stack técnica |
| [DATABASE-SCHEMA](DATABASE-SCHEMA.md) | 20 tabelas PostgreSQL + pgvector |
| [DATABASE_SETUP](DATABASE_SETUP.md) | Guia de setup PostgreSQL (extensões, URL, devcontainer vs. CI) |

## Planning

| Doc | Descrição |
|---|---|
| [USER-STORIES](USER-STORIES.md) | 12 epics, 72 stories com acceptance criteria |
| [LANGCHAIN-SKILLS-GUIDE](LANGCHAIN-SKILLS-GUIDE.md) | Quando usar cada skill LangChain/LangGraph |
| [LANGSMITH-EVALS-RESEARCH](LANGSMITH-EVALS-RESEARCH.md) | Framework de avaliação LangSmith |

## Padrão de Nova Nota

Para novas notas técnicas no vault:

1. começar com frontmatter `tags: [...]`
2. usar uma tag do conjunto canónico (`architecture`, `planning`, `agents`, `database`, `docker`, `knowledge-graph`, `evaluation`)
3. terminar com `## Related Notes`
4. incluir 3-5 links relevantes, preferindo `[[wikilinks]]` para notas do vault
5. usar link Markdown explícito apenas quando o nome for ambíguo, como `README.md`

## Epics

### Agentes

Hub notes: [[Epics/Generator agent/README|Generator agent]], [[Epics/Searcher Agent/README|Searcher agent]]

| Doc | Módulo |
|---|---|
| [US-037 Base Graph](Epics/Generator%20agent/US-037-BASE-GRAPH-EXPLAINED.md) | `agents/base.py` — StateGraph, BarrierAwareToolNode |
| [US-038 Barriers](Epics/Generator%20agent/US-038-BARRIERS-EXPLAINED.md) | `tools/barriers.py` |
| [US-039 Terminal & File](Epics/Generator%20agent/US-039-TERMINAL-FILE-EXPLAINED.md) | `tools/terminal.py`, `tools/file.py` |
| [US-040 Browser](Epics/Generator%20agent/US-040-BROWSER-TOOL-EXPLAINED.md) | `tools/browser.py` |
| [US-041 Stubs](Epics/Generator%20agent/US-041-STUBS-EXPLAINED.md) | `tools/stubs.py` |
| [US-042 Skill Loader](Epics/Generator%20agent/US-042-SKILL-LOADER-EXPLAINED.md) | `skills/loader.py` |
| [US-043 Prompt Templates](Epics/Generator%20agent/US-043-GENERATOR-PROMPTS-EXPLAINED.md) | `templates/renderer.py`, templates Jinja2 |
| [US-044 Generator Agent](Epics/Generator%20agent/US-044-GENERATOR-AGENT-EXPLAINED.md) | `agents/generator.py` — entry point funcional, integra graph + tools + skills + prompts |
| [US-054 Search Models](Epics/Searcher%20Agent/US-054-SEARCH-MODELS-EXPLAINED.md) | `models/search.py` |
| [US-055 Search Result Barrier](Epics/Searcher%20Agent/US-055-SEARCH-RESULT-BARRIER-EXPLAINED.md) | `tools/barriers.py` — search_result barrier |
| [US-056 DuckDuckGo Search Tool](Epics/Searcher%20Agent/US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED.md) | `tools/duckduckgo.py` |
| [US-057 Tavily Search Tool](Epics/Searcher%20Agent/US-057-TAVILY-SEARCH-TOOL-EXPLAINED.md) | `tools/tavily.py` |
| [US-058 search_answer Tool](Epics/Searcher%20Agent/US-058-SEARCH-ANSWER-TOOL-EXPLAINED.md) | `tools/search_memory.py` — pgvector semantic search |
| [US-059 Searcher Prompt Templates](Epics/Searcher%20Agent/US-059-Searcher-prompt-templates-EXPLAINED.md) | `templates/searcher.py`, `searcher_system.md`, `searcher_user.md` |

### Memorist Agent

Hub note: [[Epics/Memorist Agent/README|Memorist Agent]]

| Doc | Módulo |
| --- | --- |
| [US-080 MemoristResult Model](Epics/Memorist%20Agent/US-080-MEMORISTRESULT-MODEL-EXPLAINED.md) | `models/memorist.py`, `tools/barriers.py` — memorist_result barrier tool |

### Knowledge Graph

Hub note: [[Epics/Knowledge Graph/README|Knowledge Graph]]

| Doc | Módulo |
|---|---|
| [US-034 Neo4j + Graphiti Devcontainer](Epics/Knowledge%20Graph/US-034-NEO4J-GRAPHITI-DEVCONTAINER-EXPLAINED.md) | Devcontainer setup |
| [US-035 Graphiti Client](Epics/Knowledge%20Graph/US-035-GRAPHITI-CLIENT-EXPLAINED.md) | `graphiti/client.py` |
| [US-036 Graphiti Search Tool](Epics/Knowledge%20Graph/US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED.md) | `tools/graphiti_search.py` |
| [Graphiti Troubleshooting](Epics/Knowledge%20Graph/GRAPHITI-TROUBLESHOOTING.md) | diagnóstico de 500 no `/search`, healthcheck e DNS entre containers |

### Base de Dados

Hub note: [[Epics/Database/README|Database]]

| Doc | Módulo |
|---|---|
| [US-006 SQLAlchemy Pool](Epics/Database/US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED.md) | `database/connection.py` |
| [US-007 Enum Types](Epics/Database/US-007-DATABASE-ENUM-TYPES.md) | `database/enums.py` |
| [US-008 Core DB Models](Epics/Database/US-008-CORE-DB-MODELS.md) | `database/models.py` — Flow, Task, Subtask |
| [US-009 Supporting DB Models](Epics/Database/US-009-SUPPORTING-DB-MODELS-EXPLAINED.md) | `database/models.py` — Container, Toolcall, Msgchain, Termlog, Msglog |
| [US-010 Vector Store Model](Epics/Database/US-010-VECTOR-STORE-MODEL-EXPLAINED.md) | `database/models.py` + testes unit/integration/e2e para pgvector |
| [US-011 Alembic Migrations](Epics/Database/US-011-ALEMBIC-MIGRATIONS-EXPLAINED.md) | `alembic.ini`, `alembic/env.py`, migration inicial e testes unit/integration/e2e |
| [US-012 Query Functions CRUD](Epics/Database/US-012-Query-Functions-CRUD-Operations-EXPLAINED.md) | `database/queries/*.py` + fixtures/testes de integracao de queries |

### Docker Sandbox

Hub note: [[Epics/Docker Sandbox/README|Docker Sandbox]]

| Doc | Módulo |
|---|---|
| [US-013 Docker Client](Epics/Docker%20Sandbox/US-013-DOCKER-CLIENT-EXPLAINED.md) | `docker/client.py` |
| [US-014A Image Management](Epics/Docker%20Sandbox/US-014A-IMAGE-MANAGEMENT-EXPLAINED.md) | `docker/client.py` — ensure_image() |
| [US-014B Container Creation and Startup](Epics/Docker%20Sandbox/US-014B-CONTAINER-CREATION-STARTUP-EXPLAINED.md) | `docker/client.py` — run_container(), runtime config, DB lifecycle, retry |
| [US-015 Container Exec](Epics/Docker%20Sandbox/US-015-CONTAINER-EXEC-EXPLAINED.md) | `docker/client.py`, `tools/terminal.py`, `models/tool_args.py` — exec command, timeout/detach, health checks, test coverage |
| [US-016 File Operations](Epics/Docker%20Sandbox/US-016-File-Operations-EXPLAINED.md) | `docker/client.py` — read_file() / write_file() container file I/O |
| [US-017 Container Lifecycle](Epics/Docker%20Sandbox/US-017-CONTAINER-LIFECYCLE-EXPLAINED.md) | `docker/client.py` — stop_container() / remove_container() com DB sync |
| [US-018 Startup Cleanup](Epics/Docker%20Sandbox/US-018-STARTUP-CLEANUP-EXPLAINED.md) | `docker/client.py` — cleanup de containers órfãos no arranque |
| [US-019 Container Utilities](Epics/Docker%20Sandbox/US-019-CONTAINER-UTILITIES-EXPLAINED.md) | `docker/utils.py` |

### Scanner Agent

| Doc | Módulo |
|---|---|
| [US-064 Scanner Templates](Epics/Scanner%20Agent/US-064-SCANNER-TEMPLATES-EXPLAINED.md) | `templates/scanner_system.md`, `templates/scanner_user.md`, `templates/__init__.py` |
| [US-061 HackResult Model](Epics/Scanner%20Agent/US-061-HACK-RESULT-MODEL-EXPLAINED.md) | `models/hack.py`, `tools/barriers.py` — contrato de dados Scanner → Orchestrator |
| [US-062 Sploitus Search Tool](Epics/Scanner%20Agent/US-062-SPLOITUS-TOOL-EXPLAINED.md) | `tools/sploitus.py` — pesquisa de exploits no Sploitus.com |
| [US-063 Guide Tools](Epics/Scanner%20Agent/US-063-GUIDE-TOOLS-EXPLAINED.md) | `tools/guide.py` — armazenamento e busca semantica de playbooks com redacao de dados sensiveis |

### Avaliação de Agentes

Hub note: [[Epics/Agent Evaluation/README|Agent Evaluation]]

| Doc | Descrição |
|---|---|
| [EVAL-TARGETS](Epics/Agent%20Evaluation/EVAL-TARGETS.md) | Targets vulneráveis, setup, vulnerabilidades documentadas |
| [US-045 PortSwigger MVP Dataset](Epics/Agent%20Evaluation/US-045-PORTSWIGGER-MVP-DATASET-EXPLAINED.md) | Dataset MVP com 4 labs curados, subsets, ground truth |
| [US-046 PortSwigger Spinup](Epics/Agent%20Evaluation/US-046-PORTSWIGGER-SPINUP-EXPLAINED.md) | Automacao de spinup: excecoes tipadas, sessao persistida, batch mode, testes unit + e2e |
| [US-047 Generator Eval Runner](Epics/Agent%20Evaluation/US-047-GENERATOR-EVAL-RUNNER-EXPLAINED.md) | Runner de evaluacao do Generator com metricas de cobertura de plano e validacao de output estruturado |

### Searcher Agent Evaluation

| Doc | Descrição |
|---|---|
| [US-068 Searcher Eval Infra](Epics/Searcher%20Agent%20Evaluation/US-068-SEARCHER-EVAL-INFRA-EXPLAINED.md) | Infraestrutura base de avaliações, gravação de trajectories |
| [US-069 Searcher Dataset](Epics/Searcher%20Agent%20Evaluation/US-069-SEARCHER-DATASET-EXPLAINED.md) | Ground truth dataset e testes de avaliação para o agente Searcher |

## Related Notes

- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[USER-STORIES]]
- [[DATABASE-SCHEMA]]
