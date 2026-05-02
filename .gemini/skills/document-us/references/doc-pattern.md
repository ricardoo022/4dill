# LusitAI Epics Doc Pattern — Reference

Every `docs/Epics/<Epic>/<US-XXX>-<SLUG>-EXPLAINED.md` file follows the same structure.
Use this as the ground truth when generating new docs.

---

## File Name & Location

```
docs/Epics/<Epic Folder>/<US-XXX>-<SLUG>-EXPLAINED.md
```

Epic folder mapping (matches the folders already in `docs/Epics/`):

| Epic topic | Folder name |
|---|---|
| Dev Container | Dev Container |
| Database | Database |
| Docker Sandbox | Docker Sandbox |
| Knowledge Graph | Knowledge Graph |
| Generator agent | Generator agent |
| Searcher agent | Searcher agent |
| Agent Evaluation | Agent Evaluation |

When the US belongs to an epic not yet present, create the folder using the epic name from `docs/USER-STORIES.md`.

---

## Obsidian Frontmatter

Always the first thing in the file — no blank lines before it:

```markdown
---
tags: [<category>]
---
```

Valid categories:

| Tag | Use for |
|---|---|
| `architecture` | Overview/flow docs |
| `database` | PostgreSQL, SQLAlchemy, migrations, enums |
| `agents` | Agent implementation deep-dives |
| `docker` | Docker client, images, containers |
| `knowledge-graph` | Neo4j, Graphiti, graph search |
| `planning` | User stories, skill guides, research |
| `evaluation` | Eval targets, LangSmith evals |

Multiple tags allowed: `tags: [agents, docker]`.

---

## Title

```markdown
# US-XXX: <Short Description> — Explicacao Detalhada
```

First paragraph (no heading) describes in one sentence what the doc covers, naming every file it explains.

---

## Sections (in order)

### `## Contexto`

Explains **why** this module/component exists. Answers:
- What problem does it solve?
- What is it responsible for?
- How does it fit in the overall system?

Usually 4-7 bullet points or a short paragraph.

### `## Referencia PentAGI (Go)` *(optional)*

Only include when the Python code is a port of PentAGI Go code.
Show the relevant Go snippet with file path + line numbers, then explain the key difference from the Python implementation.

```markdown
### `FunctionName` (`file.go` linhas X-Y)

```go
// relevant Go snippet
```

Key difference: ...
```

### File/Class/Function sections

For each file changed, add a section like:

```markdown
## `ClassName` or `function_name` (`path/to/file.py`)
```

Inside, explain each logical block:
- Show the actual code in a fenced Python block
- Follow with a table `| Linha(s) | Explicacao |` OR `| Campo | Tipo | Descricao |`
- For constructors/init: explain each parameter
- For validators: explain what rule is enforced and why
- For methods: step-by-step numbered list of what the method does

### `## Exemplo Completo` *(include whenever the behavior has a non-trivial flow)*

Show end-to-end usage: inputs → internal steps → outputs.
Use ASCII diagrams for flows with branches. Format:

```
Step 1: ...
  → input: ...
  → output: ...

Step 2: ...
```

### `## Padrão de Implementação` *(optional)*

Include when the file establishes a reusable pattern (like barrier tools).
Shows the generic template + numbered rules that must always be followed.

### `## Questoes Frequentes` *(optional — include for complex/tricky modules)*

Format:
```
### P: Question?

A: Answer.
```

### `## Ficheiros Alterados` *(required for US docs covering multiple files)*

```markdown
## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/...` | What it contains |
```

### `## Related Notes` (REQUIRED — always include)

End with related wiki links to nearby vault notes. This is mandatory and critical for Obsidian graph/backlink navigation:

```markdown
## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[US-XXX-SLUG-EXPLAINED|Related Epic Note]]
```

**Naming rules for Related Notes:**
- Prefer Obsidian wikilinks like `[[NOTE-NAME]]` for vault notes.
- Use explicit Markdown links only when the name is ambiguous (e.g., `README.md` with multiple files).
- Link to hub notes (`Epics/*/README.md`) and related Epics docs.
- Always include `[Docs Home](../../README.md)` or similar for deep Epics paths.

---

## Style Rules

1. **Language**: Portuguese for prose, English for code and comments.
2. **Tables** for anything with 3+ fields/parameters — never prose lists for those.
3. **Code blocks** always use triple backticks with the language tag (`python`, `go`, `json`, `bash`).
4. **`---` dividers** between every top-level section.
5. **Bold** for emphasis on critical concepts (`**ponto critico**`, `**NUNCA**`).
6. ASCII diagrams using box-drawing chars (┌─┐│└┘→↓) for flows, state transitions, and call graphs.
7. Line-number references in section headings: `## `ClassName` (linhas X-Y)`.
8. Every code block shown in the doc must be the **actual** code from the diff — no paraphrasing.
9. Design decisions must be explained: "Porque e assim?" subsections justify non-obvious choices.
10. Do NOT add emojis.

---

## Tone

Aimed at a teammate reading the code for the first time. Assume they know Python and LangGraph basics but not the specific module. Explain every non-obvious decision. Use concrete examples with realistic values (e.g., real tool names, real field values like `"nmap 10.0.0.1"`).
