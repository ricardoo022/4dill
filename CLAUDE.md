# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LusitAI AI Pentest — autonomous AI-powered penetration testing engine. Direct Python port of [PentAGI](https://github.com/vxcontrol/pentagi) (Go). The Go reference lives in `pentagi/` (git submodule) for cross-referencing.

Key architectural difference from PentAGI: replaces REST+GraphQL API with an **MCP Server** (Model Context Protocol), and centralizes agent configs in `agents/` (new, not in PentAGI).

Current product scope is intentionally narrower than the full PentAGI platform: the immediate goal is a functional autonomous AI Pentest runtime first, with platform concerns (multi-user, interactive assistant/chat, per-user prompt/provider management) treated as future scope unless a User Story explicitly brings them in.

## Tech Stack

- **Python 3.12+**, async-first
- **LangChain Python 1.0+** / **LangGraph** for LLM orchestration (Claude primary, multi-provider)
- **SQLAlchemy 2.0 async** + Alembic for PostgreSQL + pgvector
- **Neo4j + Graphiti** for knowledge graph (entity relationships from scans)
- **docker-py** for Kali Linux sandbox containers
- **Pydantic v2** for all data models
- **Jinja2** for prompt templates (.md.j2 files)
- **MCP Server** as the external interface (no REST/GraphQL)

## Architecture

The system runs **12 specialized agents** that collaborate via tool-call delegation:

1. **Generator** — creates ≤15 subtasks plan from target analysis
2. **Orchestrator** — primary agent, delegates subtasks to specialists
3. **Scanner** — runs security tools in Docker container
4. **Coder** — writes custom exploit/test scripts
5. **Searcher** — web research (CVEs, techniques, documentation)
6. **Memorist** — long-term memory (pgvector)
7. **Adviser** — intervenes when agents loop (20+ calls)
8. **Installer** — installs/configures tools in Docker container at runtime
9. **Enricher** — adds context before Adviser responds (two-stage pipeline)
10. **Refiner** — adjusts plan mid-scan based on findings
11. **Reflector** — corrects agents that return text instead of tool calls
12. **Reporter** — Judge Mode validation + final JSON report + knowledge storage

**Execution flow:** MCP request → `controller/flow.py` creates Flow → spins up Kali Docker container → `controller/task.py` calls Generator for plan → loops subtasks (Orchestrator executes each, Refiner adjusts) → Reporter produces final `ScanReport` JSON.

Normal execution is autonomous. `WAITING` states are valid for operational pauses (resume via MCP, external dependency, recovery after interruption), but the runtime should not assume mandatory human intervention in the middle of a scan unless a story explicitly requires it.

**Core loop** (`agents/base.py` → `create_agent_graph`): LangGraph `StateGraph` with 2 nodes (`call_llm` + `BarrierAwareToolNode`) and conditional routing. Each agent reuses this pattern with different tools and barrier names. The `BarrierAwareToolNode` wraps LangGraph's `ToolNode` to detect "barrier" tool calls (e.g. `subtask_list` for Generator) and extract their args as the agent's result. Includes `recursion_limit` for loop prevention.

**PentAGI core loop** (`providers/perform_agent_chain`): calls LLM → gets tool_calls → executes tools → feeds results back → repeat. Includes reflection (max 3x), summarization (context too large), and loop detection (5+ same tool = abort, 20+ calls = Adviser).

## Module Responsibilities

| Module | Role | PentAGI equivalent |
|---|---|---|
| `controller/` | Scan lifecycle orchestration (flow → task → subtask) | `pkg/controller/` |
| `providers/` | LLM execution loop + agent chain | `pkg/providers/` |
| `tools/` | Tool registry, executor, handlers (terminal, search, memory, browser, web search) | `pkg/tools/` |
| `docker/` | Kali container management (create, exec, file I/O, stop, destroy) | `pkg/docker/` |
| `database/` | Persistence (flows, tasks, subtasks, containers, toolcalls, msgchains, termlogs, msglogs, vector_store) | `pkg/database/` |
| `graphiti/` | Neo4j knowledge graph client | `pkg/graphiti/` |
| `templates/` | Jinja2 prompt templates, one .md.j2 per agent | `pkg/templates/prompts/` |
| `skills/` | FASE skill index loader (SKILL.md frontmatter parsing for Generator + Scanner) — **new** | n/a |
| `agents/` | Agent configs (tools, limits, delegation targets) — **new** | spread across Go code |
| `mcp/` | MCP Server entry point (replaces REST+GraphQL) | `pkg/server/` + `pkg/graph/` |
| `models/` | Pydantic models shared across modules | inline in Go packages |
| `recon/` | FASE 0 backend detection (Supabase, Firebase, Custom API, subdomains) — **new** | n/a (SecureDev-only) |

## Commands

```bash
# Install (editable mode with dev deps)
pip install -e ".[dev]"

# Lint (ruff: line-length=100, rules: E,F,W,I,N,UP,B,A,SIM,TCH, ignores E501)
ruff check src/ tests/
ruff format --check src/ tests/

# Type check
mypy src/pentest/ --ignore-missing-imports

# Tests by layer
pytest tests/unit/ -v                           # Unit (no deps, fast)
pytest tests/integration/ -v -m integration     # Integration (needs PostgreSQL + Docker)
pytest tests/agent/ -v -m agent                 # Agent (mocked LLM)
pytest tests/e2e/ -v -m e2e                     # E2E (manual only, needs API keys)

# Single test
pytest tests/unit/database/test_models.py::TestFlowModel::test_flow_tablename -v

# Coverage
pytest tests/ --ignore=tests/e2e/ --cov=src/pentest --cov-report=term-missing

# Alembic migrations (run inside devcontainer where DATABASE_URL is set)
alembic upgrade head        # apply all pending migrations
alembic downgrade base      # roll back everything
alembic current             # show active migration version
alembic check               # verify models and schema are in sync
alembic revision --autogenerate -m "short_description"  # generate migration from model changes
```

## DevContainer

Runs via docker-compose with four services: **app** (Python devcontainer), **db** (pgvector/pg16), **neo4j** (community edition), **graphiti** (zepai/graphiti). Key env vars:
- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/lusitaidb`
- `DOCKER_INSIDE=true` (indicates running inside devcontainer)
- `GRAPHITI_ENABLED=true`, `GRAPHITI_URL=http://graphiti:8000`, `GRAPHITI_TIMEOUT=30`
- `NEO4J_URI=bolt://neo4j:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=changeme`

Forwarded ports: 5432 (PostgreSQL), 7474 (Neo4j browser), 7687 (Bolt), 8000 (Graphiti API).

The `postCreateCommand` installs the project in editable mode and runs `pre-commit install` automatically — no manual setup needed.

`docker/init-db.sql` runs on first container start and pre-installs the `vector` and `uuid-ossp` PostgreSQL extensions into `lusitaidb`, so `create_vector_extension()` is effectively a no-op in the devcontainer (it still needs calling in CI and production where the extension isn't pre-installed).

**Integration test DB names differ:** the devcontainer DB is `lusitaidb`; CI uses `testdb`. Integration tests default to `pentagidb_test` when `DATABASE_URL` is unset. Always set `DATABASE_URL` explicitly when running integration tests outside the devcontainer.

## Testing Strategy

Five test layers, mapped to User Story acceptance criteria (see `/test-us` skill):

| Layer | Directory | Marker | Dependencies | CI |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | *(none)* | None | Always |
| **Integration** | `tests/integration/` | `@pytest.mark.integration` | PostgreSQL (testcontainers), Docker | Always |
| **Agent** | `tests/agent/` | `@pytest.mark.agent` | Mocked LLM (respx) | Always |
| **E2E** | `tests/e2e/` | `@pytest.mark.e2e` | Real LLM + Docker + target | Manual only (`workflow_dispatch`) |
| **Evals** | `tests/evals/` | *(none)* | Real LLM + PortSwigger spinup | Manual only |

Test stack: pytest, pytest-asyncio, pytest-cov, pytest-mock, pytest-timeout, testcontainers, polyfactory, respx, freezegun, playwright.

**RULE — When a test fails, never change the test just to make it pass.** First determine whether the bug is in the production code or genuinely in the test itself (wrong assertion, stale fixture, incorrect expectation). Only modify a test if the test was wrong about what the code should do. If the code is wrong, fix the code. If it is unclear, stop and ask before touching either.

## Git Workflow

- **Branch:** `main` (protected — no direct push)
- **Flow:** `feature/US-XXX-description` branch → PR → CI passes → 1 review → merge
- **CI:** GitHub Actions runs lint + unit + integration + agent on every PR. `ci-pass` is the single required check for branch protection — do not require individual jobs. PRs that only touch `docs/**` or `*.md` skip CI entirely.
- **E2E tests:** Manual only — triggered via `workflow_dispatch`. Not run automatically on push to `main`.
- **Naming:** branches follow `feature/US-XXX-short-description`
- **Pre-commit:** hooks (ruff, format, trailing whitespace, no-commit-to-main) run automatically on every `git commit`. Installed via devcontainer `postCreateCommand`. Outside devcontainer: `pip install pre-commit && pre-commit install`.

## Submodules

- `pentagi/` — PentAGI Go reference implementation (read-only, for cross-referencing)
- `lusitai-internal-scan/` — security scanning engine with FASE 0-21 skill phases

Clone with submodules: `git clone --recurse-submodules`

## Skills

LangChain/LangGraph official skills (use when implementing the agent engine):
- `/framework-selection` — choose LangChain vs LangGraph vs Deep Agents
- `/langchain-dependencies` — package versions for pyproject.toml
- `/langchain-fundamentals` — create_agent(), @tool, middleware
- `/langgraph-fundamentals` — StateGraph, nodes, edges (core of agent chain)
- `/langgraph-persistence` — checkpointers, thread_id, Store
- `/langgraph-human-in-the-loop` — interrupt(), Command(resume=...)
- `/langchain-rag` — vector stores, embeddings (for Memorist)
- `/langchain-middleware` — intercept tool calls, error handling

Project skills:
- `/test-us US-XXX` — generate tests from User Story acceptance criteria
- `/review` — pre-landing PR review
- `/approve-pr` — full PR review with verdict against the User Story
- `/document-release` — sync top-level docs after shipping
- `/document-us` — generate EXPLAINED.md for the shipped User Story

See `docs/LANGCHAIN-SKILLS-GUIDE.md` for detailed usage guide.

## Documentation

Every `.md` file created inside `docs/` **must** start with Obsidian frontmatter:

```markdown
---
tags: [<category>]
---
```

Valid categories and when to use each:

| Tag | Use for |
|---|---|
| `architecture` | Overview/flow docs (agents, execution, project structure) |
| `database` | PostgreSQL schema, SQLAlchemy, migrations, enums |
| `agents` | Agent implementation deep-dives (US-0XX-...-EXPLAINED.md) |
| `docker` | Docker client, image management, container utilities |
| `knowledge-graph` | Neo4j, Graphiti, graph search |
| `planning` | User stories, skill guides, research |
| `evaluation` | Eval targets, LangSmith evals |

A file may have multiple tags when it genuinely spans categories (e.g. `tags: [agents, docker]`).
The docs index is `docs/README.md`, which uses `tags: [home]` and must be kept up to date whenever a new doc is added.

Every technical note added under `docs/` should also end with a `## Related Notes` section containing 3-5 links to nearby vault notes. Prefer Obsidian wikilinks for vault notes, and use explicit Markdown links only when the target name would be ambiguous (for example multiple `README.md` files).

Detailed architecture docs (Portuguese) in `docs/`:
- `AGENT-ARCHITECTURE.md` — agent roles, tools, delegation model, example workflows
- `EXECUTION-FLOW.md` — 7-phase scan lifecycle with DB state at each step
- `PROJECT-STRUCTURE.md` — full PentAGI→Python mapping, module explanations
- `USER-STORIES.md` — 12 epics, 72 stories with acceptance criteria
- `DATABASE-SCHEMA.md` — PostgreSQL + pgvector schema design
- `LANGCHAIN-SKILLS-GUIDE.md` — when to use each LangChain skill
- `LANGSMITH-EVALS-RESEARCH.md` — LangSmith evaluation framework research
- `README.md` — docs index for Obsidian navigation
- `Epics/Generator agent/US-037-BASE-GRAPH-EXPLAINED.md` — line-by-line explanation of base graph pattern
- `Epics/Generator agent/US-038-BARRIERS-EXPLAINED.md` — barrier tool pattern (how agents signal completion)
- `Epics/Generator agent/US-039-TERMINAL-FILE-EXPLAINED.md` — terminal and file tools (Docker factory closures)
- `Epics/Generator agent/US-040-BROWSER-TOOL-EXPLAINED.md` — browser tool (HTTP content fetching)
- `Epics/Generator agent/US-041-STUBS-EXPLAINED.md` — memorist/searcher stub tools
- `Epics/Generator agent/US-042-SKILL-LOADER-EXPLAINED.md` — skill index loader (SKILL.md frontmatter parsing)
- `Epics/Generator agent/US-043-GENERATOR-PROMPTS-EXPLAINED.md` — Jinja2 prompt renderer, template variables, scan_path injection
- `Epics/Generator agent/US-044-GENERATOR-AGENT-EXPLAINED.md` — full Generator agent: LLM resolution, skill loading, graph construction
- `Epics/Knowledge Graph/US-034-NEO4J-GRAPHITI-DEVCONTAINER-EXPLAINED.md` — Neo4j + Graphiti devcontainer setup
- `Epics/Knowledge Graph/US-035-GRAPHITI-CLIENT-EXPLAINED.md` — Graphiti async HTTP client
- `Epics/Knowledge Graph/US-036-GRAPHITI-SEARCH-TOOL-EXPLAINED.md` — Graphiti search LangChain tool
- `Epics/Knowledge Graph/GRAPHITI-TROUBLESHOOTING.md` — common Graphiti/Neo4j issues and fixes
- `Epics/Database/US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED.md` — async connection pool implementation details
- `Epics/Database/US-007-DATABASE-ENUM-TYPES.md` — PostgreSQL enum types + SQLAlchemy wrappers
- `Epics/Database/US-008-CORE-DB-MODELS.md` — Flow/Task/Subtask SQLAlchemy 2.0 models, cascade delete, soft-delete, indexes
- `Epics/Database/US-009-SUPPORTING-DB-MODELS-EXPLAINED.md` — Toolcall, Msgchain, Termlog, Msglog SQLAlchemy models
- `Epics/Database/US-010-VECTOR-STORE-MODEL-EXPLAINED.md` — VectorStore model, pgvector embedding column, ivfflat index
- `Epics/Database/US-011-ALEMBIC-MIGRATIONS-EXPLAINED.md` — Alembic async env, initial migration design, idempotency, trigger function, ivfflat index
- `Epics/Database/US-012-Query-Functions-CRUD-Operations-EXPLAINED.md` — database/queries/ CRUD modules (8 modules, typed params, async query functions)
- `Epics/Docker Sandbox/US-013-DOCKER-CLIENT-EXPLAINED.md` — Docker client init, config, network setup, DinD host_dir resolution
- `Epics/Docker Sandbox/US-014A-IMAGE-MANAGEMENT-EXPLAINED.md` — ensure_image() flow: cache hit, pull with timeout, fallback logic, DockerImageError
- `Epics/Docker Sandbox/US-014B-CONTAINER-CREATION-STARTUP-EXPLAINED.md` — run_container() flow: DB lifecycle (STARTING→RUNNING/FAILED), port bindings, CRC32 hostname, volume setup, bridge/host networking, image fallback retry
- `Epics/Docker Sandbox/US-015-CONTAINER-EXEC-EXPLAINED.md` — exec_command() with timeout and detach support
- `Epics/Docker Sandbox/US-016-File-Operations-EXPLAINED.md` — read_file() / write_file() container file I/O
- `Epics/Docker Sandbox/US-017-CONTAINER-LIFECYCLE-EXPLAINED.md` — stop_container() / remove_container() with DB sync
- `Epics/Docker Sandbox/US-018-STARTUP-CLEANUP-EXPLAINED.md` — container startup cleanup and recovery on boot
- `Epics/Docker Sandbox/US-019-CONTAINER-UTILITIES-EXPLAINED.md` — container naming and port allocation utilities
- `Epics/Agent Evaluation/EVAL-TARGETS.md` — vulnerable test targets by backend type
- `Epics/Agent Evaluation/US-045-PORTSWIGGER-MVP-DATASET-EXPLAINED.md` — PortSwigger MVP dataset design and lab selection
- `Epics/Agent Evaluation/US-046-PORTSWIGGER-SPINUP-EXPLAINED.md` — PortSwigger lab spinup automation and eval harness
- `Epics/Searcher Agent/US-054-SEARCH-MODELS-EXPLAINED.md` — SearchResult, SearchAction, ComplexSearch, SearchAnswerAction Pydantic models
- `Epics/Searcher Agent/US-055-SEARCH-RESULT-BARRIER-EXPLAINED.md` — search_result barrier tool, coexistence with subtask_list, graph integration
- `Epics/Searcher Agent/US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED.md` — DuckDuckGo web search tool and availability checks
- `Epics/Searcher Agent/US-057-TAVILY-SEARCH-TOOL-EXPLAINED.md` — Tavily web search tool with answer + ranked sources
- `Epics/Searcher Agent/US-058-SEARCH-ANSWER-TOOL-EXPLAINED.md` — create_search_answer_tool() pgvector semantic search for Memorist
- `Epics/Searcher Agent/US-059-Searcher-prompt-templates-EXPLAINED.md` — render_searcher_prompt(), searcher_system.md.j2 / searcher_user.md.j2
- `Epics/Scanner Agent/US-061-HACK-RESULT-MODEL-EXPLAINED.md` — HackResult Pydantic model for Scanner agent output
- `Epics/Scanner Agent/US-062-SPLOITUS-TOOL-EXPLAINED.md` — Sploitus.com exploit search tool, result formatting, truncation

## Development Notes

- Project is in early implementation — several `src/pentest/` modules are still `__init__.py` stubs (`controller/`, `mcp/`, `providers/` except factory.py, `agents/` except base.py + generator.py)
- **Implemented modules:**
  - `config.py` — `LLMConfig` Pydantic model; reads provider + model from env vars (`LLM_PROVIDER`, `LLM_MODEL`, per-agent overrides like `GENERATOR_LLM_MODEL`); used by `providers/factory.py`
  - `providers/factory.py` — `create_chat_model()` factory + `resolve_provider_config()`; supports Anthropic and OpenAI; selects provider and model per agent via `LLMConfig`
  - `recon/` — backend detection (supabase, firebase, custom_api, subdomains, orchestrator)
  - `agents/base.py` — LangGraph base graph pattern (BarrierAwareToolNode, AgentState, create_agent_graph)
  - `agents/generator.py` — full Generator agent: resolves LLM via `providers/factory.py`, loads FASE skill index, renders prompt via `templates/renderer.py`, builds tool list, calls `create_agent_graph()`
  - `models/` — subtask.py, recon.py, tool_args.py, search.py (Pydantic schemas; search.py has `SearchResult`, `SearchAction`, `ComplexSearch`, `SearchAnswerAction`), hack.py (`HackResult` with `result` + `message` fields for Scanner output)
  - `tools/` — barriers.py (`subtask_list` + `search_result`), terminal.py, file.py (Docker execution via factory closures), browser.py (HTTP content fetching), stubs.py (memorist/searcher placeholders), graphiti_search.py (Graphiti knowledge graph search), duckduckgo.py (DuckDuckGo web search), tavily.py (Tavily web search), search_memory.py (`create_search_answer_tool()` pgvector semantic search for Memorist), sploitus.py (Sploitus.com exploit search with result formatting/truncation), registry.py (tool registry dataclasses)
  - `skills/loader.py` — `load_fase_index()` parses SKILL.md frontmatter for Generator prompt injection; `load_fase_skill()` loads full SKILL.md for Scanner
  - `database/connection.py` — async engine init, session context manager, connection pool (pool_size=10, max_overflow=20)
  - `database/exceptions.py` — `DatabaseConnectionError` with hostname/port context
  - `database/enums.py` — 10 PostgreSQL StrEnum types + SQLAlchemy wrappers (all with `values_callable` for lowercase serialization)
  - `database/models.py` — `Flow`, `Task`, `Subtask`, `Container`, `Toolcall`, `Msgchain`, `Termlog`, `Msglog`, `VectorStore` SQLAlchemy 2.0 models; cascade delete, soft-delete (`deleted_at`), timezone-aware timestamps, ivfflat index on `VectorStore.embedding`; `create_vector_extension(AsyncConnection)` helper
  - `database/queries/` — 8 CRUD modules: containers.py, flows.py, msgchains.py, msglogs.py, subtasks.py, tasks.py, termlogs.py, toolcalls.py; each exports `Create*Params` dataclass + typed async query functions (create, get, list)
  - `alembic/` — fully configured: `alembic.ini` (env-driven URL), async `env.py`, `versions/001_initial_schema.py` (all 9 runtime tables, 10 enums, 6 triggers, ivfflat index, pgvector extension)
  - `templates/renderer.py` — `render_generator_prompt()` using Jinja2; templates live in `templates/prompts/` as `.md.j2` files (currently `generator_system.md.j2`, `generator_user.md.j2`)
  - `templates/searcher.py` — `render_searcher_prompt()` stub for the Searcher agent (searcher `.md.j2` templates not yet created)
  - `graphiti/` — config.py (env-based settings), client.py (async HTTP client with 7 search methods), models.py (typed request/response models), local_fallback.py (local Neo4j fallback for ingestion/search when Graphiti server is unavailable; regex-based entity extraction for hosts, CVEs, ports, credentials, URLs, products)
  - `docker/utils.py` — container naming (`primary_terminal_name`) and deterministic port allocation (`get_primary_container_ports`)
  - `docker/client.py` — `DockerClient` with `ensure_image()` (cache → pull → fallback → `DockerImageError`), `_pull_image()` with configurable timeout via `ThreadPoolExecutor`, `DockerConfig.pull_timeout` (default 300s); `run_container()` creates and starts a flow container with full DB lifecycle (STARTING → RUNNING / FAILED), deterministic port bindings, CRC32 hostname, volume setup, bridge/host networking, and image fallback retry; `exec_command(container_id, cmd, timeout, detach)` runs commands inside a running container; `read_file(container_id, path)` / `write_file(container_id, path, content)` for container file I/O; `stop_container(container_id)` / `remove_container(container_id)` with DB sync (RUNNING → STOPPED / REMOVED); helpers: `_crc32_hostname()`, `_resolve_flow_paths()`, `_build_port_bindings()`, `_build_volumes()`, `_build_run_kwargs()`
  - `docker/config.py` — `DockerConfig` Pydantic model with `pull_timeout: int = 300`
  - `docker/exceptions.py` — `DockerConnectionError`, `DockerImageError`
- `.devcontainer/` is configured and functional
- Documentation language is Portuguese; code and comments should be in English
- When translating from PentAGI Go, preserve the same behavior unless explicitly noted
- `asyncio_mode = "auto"` in pytest config — no need for `@pytest.mark.asyncio` on async tests
- Database scope is intentionally narrowed to the current runtime: implement execution, audit, recovery, and observability first. Do not proactively add multi-user tables, assistant tables, provider tables, or prompt override tables unless the current task explicitly requires them.
- For database enums and docs, treat `WAITING` as an operational pause state, not proof of human-in-the-loop product behavior.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Full PR review with verdict (aprovar PR, analisar PR, review this PR, dar veredicto) → invoke approve-pr
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Generate EXPLAINED.md doc for a shipped US → invoke document-us
- Generate tests from user story → invoke test-us
- Create a new skill → invoke skill-creator
- Which framework to use (LangChain vs LangGraph vs Deep Agents) → invoke framework-selection
- Package versions, dependency setup → invoke langchain-dependencies
- Agent creation, @tool, middleware → invoke langchain-fundamentals
- StateGraph, nodes, edges → invoke langgraph-fundamentals
- Checkpointers, thread_id, Store → invoke langgraph-persistence
- interrupt(), Command(resume=...) → invoke langgraph-human-in-the-loop
- Vector stores, embeddings, RAG → invoke langchain-rag
- Intercept tool calls, error handling → invoke langchain-middleware
- Deep Agents harness, create_deep_agent() → invoke deep-agents-core
- Deep Agents memory, StateBackend, StoreBackend → invoke deep-agents-memory
- Subagents, task planning, HITL → invoke deep-agents-orchestration
