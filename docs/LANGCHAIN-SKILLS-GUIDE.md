---
tags: [planning]
---

# LangChain Skills Guide

> Guia de quando usar cada skill do LangChain instalada em `.claude/skills/`.

---

## Skills Instaladas

11 skills oficiais do [langchain-ai/langchain-skills](https://github.com/langchain-ai/langchain-skills), instaladas localmente no projeto.

| Skill | Foco |
|-------|------|
| `framework-selection` | Escolher LangChain vs LangGraph vs Deep Agents |
| `langchain-dependencies` | Packages, versoes, setup de projecto |
| `langchain-fundamentals` | `create_agent()`, `@tool`, middleware base |
| `langchain-middleware` | Human-in-the-loop, intercept tool calls, retry |
| `langchain-rag` | RAG pipelines, vector stores, embeddings |
| `langgraph-fundamentals` | StateGraph, nodes, edges, Command, Send, streaming |
| `langgraph-persistence` | Checkpointers, thread_id, Store, time travel |
| `langgraph-human-in-the-loop` | `interrupt()`, `Command(resume=...)`, approval flows |
| `deep-agents-core` | Deep Agents harness, SKILL.md, configuracao |
| `deep-agents-memory` | StateBackend, StoreBackend, FilesystemMiddleware |
| `deep-agents-orchestration` | SubAgentMiddleware, TodoList, task delegation |

---

## Fase 0 — Antes de Escrever Codigo

### `/framework-selection`

**Quando:** Primeiro de tudo, antes de qualquer implementacao.

**Para que:** Decidir se o `perform_agent_chain` usa LangGraph StateGraph, LangChain puro, ou Deep Agents. Os tres sao camadas, nao alternativas:

```
Deep Agents        ← batteries included (planning, memory, skills)
  LangGraph        ← orchestration (graphs, loops, state)
    LangChain      ← foundation (models, tools, prompts)
```

**No projecto:** Decidir a stack do engine de orquestracao dos 10 agentes.

---

### `/langchain-dependencies`

**Quando:** Ao criar o `pyproject.toml`.

**Para que:** Saber que packages instalar, versoes minimas, como estruturar dependencias. Cobre LangChain 1.0 (LTS), langchain-core, providers (anthropic, openai), e ferramentas comunitarias.

**No projecto:** Setup inicial — definir `langchain>=1.0`, `langchain-anthropic`, `langgraph`, etc.

---

## Fase 1 — Core do Engine

### `/langgraph-fundamentals` (MAIS USADA)

**Quando:** Ao implementar o agent chain loop em `src/pentest/providers/`.

**Para que:** StateGraph, nodes, edges, conditional routing, Command, Send, invoke, streaming, error handling. E o core de como construir workflows de agentes como grafos.

**No projecto:**
- `perform_agent_chain` — o loop LLM -> tool_calls -> execute -> repeat
- Routing condicional: Orchestrator decide Scanner vs Coder vs Searcher
- State management: contexto da subtask, resultados acumulados
- Send: delegacao paralela a multiplos especialistas

---

### `/langchain-fundamentals`

**Quando:** Ao definir tools e criar agentes em `src/pentest/tools/` e `src/pentest/agents/`.

**Para que:** `create_agent()`, `@tool` decorator, tool binding, middleware patterns. A forma correcta de definir tools e agentes em LangChain 1.0+.

**No projecto:**
- Definir `terminal`, `file`, `browser` como `@tool`
- Tools de delegacao (`scanner`, `coder`, `searcher`) como tool calls
- Barrier tools (`done`, `hack_result`, `subtask_list`) como tools com side effects
- Criar cada um dos 10 agentes com `create_agent()`

---

### `/langgraph-persistence`

**Quando:** Ao implementar checkpointing e estado em `src/pentest/database/`.

**Para que:** Checkpointers (PostgreSQL), thread_id por subtask, Store para memoria cross-thread, time travel para recovery.

**No projecto:**
- Um thread por subtask execution
- Guardar estado entre subtasks (execution context)
- Recovery apos crash — retomar de onde parou
- Store para dados partilhados entre agentes (configs descobertas, keys)

---

## Fase 2 — Features Avancadas

### `/langchain-middleware`

**Quando:** Ao implementar o Reflector, filtro de comandos destrutivos, e error handling.

**Para que:** Intercept tool calls antes de executar, human-in-the-loop approval, Command resume, retry logic, structured output com Pydantic.

**No projecto:**
- **Filtro de comandos:** middleware que intercepts `terminal` tool calls e bloqueia comandos destrutivos (DROP, DELETE, msfconsole)
- **Reflector:** middleware que detecta respostas sem tool calls e forca re-tentativa
- **Ask barrier:** pausa execucao e pede input ao user via MCP
- **Structured output:** Reporter gera `ScanReport` validado contra Pydantic

---

### `/langgraph-human-in-the-loop`

**Quando:** Ao implementar barriers (`ask`, `done`) e intervencao do Adviser.

**Para que:** `interrupt()` pausa o grafo, `Command(resume=value)` retoma com input. Requer checkpointer + thread_id.

**No projecto:**
- `ask` barrier: Scanner/Orchestrator pede input ao utilizador
- Adviser/Mentor: intervencao automatica quando agente esta preso (20+ tool calls)
- Ownership verification: pausa scan se verificacao falha, retoma quando confirmado

---

### `/langchain-rag`

**Quando:** Ao implementar o Memorist e vector DB em `src/pentest/database/` e `src/pentest/tools/`.

**Para que:** Document loaders, text splitters, embeddings, vector stores (pgvector). Pipeline completo de RAG.

**No projecto:**
- **Memorist agent:** pesquisa semantica no vector DB (pgvector)
- Guardar conhecimento de scans anteriores ("apps Lovable tem PDF.js desatualizado")
- `search_in_memory` tool: query semantica
- `store_guide` / `store_answer` / `store_code`: indexar novo conhecimento
- Embeddings via Anthropic ou Voyage AI

---

## Fase 3 — Orquestracao Multi-Agente

### `/deep-agents-orchestration`

**Quando:** Ao implementar delegacao Orchestrator -> especialistas e o plano do Generator.

**Para que:** SubAgentMiddleware (`task` tool), TodoListMiddleware (`write_todos`), task planning, delegation patterns.

**No projecto:**
- Orchestrator delega para Scanner, Coder, Searcher via SubAgent pattern
- Generator cria plano de subtasks (equivalente a TodoList)
- Refiner ajusta subtasks restantes (patch ao plano)

---

### `/deep-agents-memory`

**Quando:** Ao implementar memoria persistente cross-scan.

**Para que:** StateBackend (efemero, por thread), StoreBackend (persistente, cross-thread), CompositeBackend (routing), FilesystemMiddleware.

**No projecto:**
- StateBackend: working memory de cada subtask
- StoreBackend: conhecimento acumulado entre scans (pgvector)
- CompositeBackend: routing — ficheiros temporarios no container, conhecimento permanente na DB

---

### `/deep-agents-core`

**Quando:** Se decidires usar o Deep Agents framework como base do engine.

**Para que:** `create_deep_agent()` com planning, memory, skills, e filesystem built-in. Harness completo que abstrai muito do boilerplate.

**No projecto:** Avaliar se compensa usar Deep Agents como base (mais opinativo mas menos codigo custom) vs LangGraph puro (mais flexivel mas mais trabalho).

---

## Resumo Visual

```
Inicio do projecto
  |
  |-- /framework-selection        <- "que framework usar?"
  |-- /langchain-dependencies     <- "que packages instalar?"
  |
  v
Implementar agent chain
  |
  |-- /langgraph-fundamentals     <- StateGraph, nodes, edges (MAIS USADA)
  |-- /langchain-fundamentals     <- tools, create_agent()
  |
  v
Persistencia + memoria
  |
  |-- /langgraph-persistence      <- checkpoints, thread_id
  |-- /langchain-rag              <- vector store, Memorist
  |
  v
Controlo + seguranca
  |
  |-- /langchain-middleware        <- filtro comandos, reflector
  |-- /langgraph-human-in-the-loop <- barriers, ask, interrupt
  |
  v
Multi-agent avancado
  |
  |-- /deep-agents-orchestration   <- subagents, planning
  |-- /deep-agents-memory          <- cross-thread memory
  '-- /deep-agents-core            <- framework completo (opcional)
```

---

## Top 3 — As Mais Importantes

1. **`/langgraph-fundamentals`** — core do engine, vais usar em tudo que envolva o agent chain
2. **`/langchain-fundamentals`** — definicao de tools e agentes, segundo mais usado
3. **`/langchain-rag`** — Memorist e vector DB, essencial para o sistema aprender entre scans

---

## Related Notes

- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[USER-STORIES]]
- [[US-037-BASE-GRAPH-EXPLAINED]]
- [[LANGSMITH-EVALS-RESEARCH]]
