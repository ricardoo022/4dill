# LusitAI - AI Pentest

Autonomous AI-powered penetration testing engine. Direct Python port of [PentAGI](https://github.com/vxcontrol/pentagi), replacing REST+GraphQL with an MCP Server interface.

The current scope is intentionally narrower than the full PentAGI platform: the immediate goal is a functional autonomous AI Pentest runtime first. Platform features such as multi-user support, interactive assistant/chat flows, and per-user provider/prompt management are treated as future scope unless a specific user story brings them in.

## Quick Start

You are recommended to open the project with devcontainer, or use the following simplified approach.

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/ricardoo022/lusitai-aipentest.git
cd lusitai-aipentest

# Install
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v -m integration
pytest tests/agent/ -v -m agent
```

## Architecture

12 specialized agents collaborate via tool-call delegation:

**Generator** (plan) → **Orchestrator** (delegate) → **Scanner** / **Coder** / **Searcher** (execute) → **Refiner** (adjust) → **Reporter** (validate + JSON output)

Supporting agents: **Memorist** (long-term memory), **Adviser** (unstuck loops), **Installer** (tool setup), **Enricher** (context enrichment), **Reflector** (force tool usage)

Normal execution is autonomous. When a scan enters `WAITING`, that should be read as an operational pause such as MCP resume, external dependency, or recovery after interruption, not as mandatory human intervention during the normal scan flow.

## Tech Stack

- Python 3.12+, async-first
- LangChain / LangGraph for agent orchestration
- SQLAlchemy 2.0 async + PostgreSQL + pgvector
- Neo4j + Graphiti for knowledge graph
- docker-py for Kali Linux sandbox containers
- Pydantic v2 for all data models
- MCP Server as external interface

## Project Structure

```
src/pentest/
    controller/    # Scan lifecycle (flow, task, subtask)
    providers/     # LLM execution loop + agent chain
    agents/        # Agent configs (tools, limits, delegation targets)
    tools/         # Tool registry, executor, handlers (terminal, browser, graph, web search)
    recon/         # FASE 0 backend detection (Supabase, Firebase, Custom API, subdomains)
    docker/        # Kali container management
    database/      # Runtime persistence: flows, tasks, subtasks, audit logs, vector store
    graphiti/      # Neo4j knowledge graph client
    templates/     # Jinja2 prompt templates per agent
    models/        # Pydantic models shared across modules
    mcp/           # MCP Server entry point
tests/
    unit/          # No deps, fast
    integration/   # Real PostgreSQL + Docker
    agent/         # Mocked LLM
    e2e/           # Full scan flow (real LLM + Docker; runs on push to main)
```

Each module has a `README.md` with file descriptions, responsibilities, and import rules.

## Git Workflow

1. Create branch: `git checkout -b feature/US-XXX-description`
2. Implement + write tests
3. Push and open PR
4. CI runs (lint + unit + integration + agent tests)
5. 1 review required → merge to `main`

## Submodules

- `pentagi/` — PentAGI Go reference (read-only, for cross-referencing)
- `lusitai-internal-scan/` — security scanning engine with FASE 0-21

## Documentation

- [Agent Architecture](docs/AGENT-ARCHITECTURE.md) — 12 agents, tools, roles, context passing
- [Execution Flow](docs/EXECUTION-FLOW.md) — step-by-step scan lifecycle, working memory, persistence
- [Project Structure](docs/PROJECT-STRUCTURE.md) — folder structure, tech stack, PentAGI mapping
- [User Stories](docs/USER-STORIES.md) — 12 epics, 72 stories with acceptance criteria
- [Database Schema](docs/DATABASE-SCHEMA.md) — PostgreSQL + pgvector schema design

Note: `docs/DATABASE-SCHEMA.md` documents the full PentAGI schema as a reference. The current LusitAI implementation intentionally uses a narrower runtime-focused subset; see `docs/USER-STORIES.md` for the scoped implementation plan.
- [LangChain Skills Guide](docs/LANGCHAIN-SKILLS-GUIDE.md) — when to use each LangChain skill
- [LangSmith Evals Research](docs/LANGSMITH-EVALS-RESEARCH.md) — LangSmith evaluation framework research
- [Docs Index](docs/README.md) — Obsidian-friendly index for all project docs
- [Epics/](docs/Epics/) — per-US deep-dive EXPLAINED.md files (Database, Docker Sandbox, Generator agent, Knowledge Graph, Searcher agent, Agent Evaluation)

## License

Proprietary. All rights reserved.
