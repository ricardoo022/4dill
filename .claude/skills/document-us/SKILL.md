---
name: document-us
description: "Generates a detailed EXPLAINED.md in docs/Epics/ for the User Story implemented on the current branch. Reads the git diff and produces deep, line-by-line documentation following the project's established Epics pattern: Portuguese prose, fenced code blocks, field tables, and ASCII diagrams. This skill should be used when the user asks to document the US, write the doc before the PR, or create the EXPLAINED.md."
---

# document-us

Generate a detailed `EXPLAINED.md` doc in `docs/Epics/` for the User Story implemented on
the current branch, following the project's established documentation pattern.

---

## When to invoke

Invoke this skill when the user says:
- "document the US before the PR"
- "write the doc / create the EXPLAINED.md"
- "document what was done"
- "gerar a doc do US-XXX"

---

## Workflow

Follow these steps **in order**.

### Step 1 — Identify the User Story

1. Run `git branch --show-current` to get the branch name.
   - Branch format: `feature/US-XXX-short-description` — extract `US-XXX`.
2. Run `git diff main...HEAD --stat` to see which files changed.
3. Run `git log main...HEAD --oneline` to read commit messages.
4. Open `docs/USER-STORIES.md` and locate the US by number.
   - Read its **Story**, **Acceptance Criteria**, **Technical Notes**, and **Tests Required** sections.
   - Note the **Epic** name — this determines the target folder.

### Step 2 — Read every changed source file

For each file in the diff (source files in `src/` and `tests/`):
1. Read the full file with the Read tool.
2. Run `git diff main...HEAD -- <file>` to see exactly what changed.
3. Note: explain **only the code that was added or modified**, not pre-existing code — unless
   the pre-existing code is essential context for understanding the new code.

### Step 3 — Determine doc location and name

- Folder: `docs/Epics/<Epic Folder>/`
  - Use the epic name from `docs/USER-STORIES.md`.
  - If the folder does not exist, create it.
- File name: `US-XXX-<SLUG>-EXPLAINED.md`
  - `<SLUG>` is a short ALL-CAPS hyphen-separated description of what was implemented.
  - Examples: `SEARCH-MODELS`, `DOCKER-CLIENT`, `BASE-GRAPH`, `BARRIERS`.

### Step 4 — Generate the documentation

Follow the pattern in `references/doc-pattern.md` exactly. Key requirements:

**Mandatory sections (every doc):**
1. Obsidian frontmatter `---\ntags: [<category>]\n---`
2. Title `# US-XXX: <Description> — Explicacao Detalhada`
3. Intro sentence (no heading) naming every file explained
4. `## Contexto` — why this module exists, responsibilities, system fit
5. One section per file/class/function with:
    - Actual code from the diff in fenced code blocks
    - Tables explaining each field, parameter, or line range
    - Step-by-step numbered explanations for non-trivial methods
6. `## Ficheiros Alterados` table when more than one file changed
7. `## Related Notes` — Obsidian wiki links to nearby vault notes (REQUIRED)

**Cross-references (mandatory for the closing section):**
- Use `[[US-XXX-SLUG-EXPLAINED]]` (Obsidian wikilink, no `.md` extension) for every related doc.
- **Never** use `**bold**` for doc references — Obsidian ignores bold; only `[[wikilinks]]` create graph edges.
- Use backtick paths `` **`src/pentest/.../file.py`** `` for source file references (not docs).

**Include when applicable:**
- `## Referencia PentAGI (Go)` — when the code ports a Go module (check `pentagi/` submodule)
- `## Exemplo Completo` — for any non-trivial execution flow
- `## Padrao de Implementacao` — when a reusable pattern is established
- `## Questoes Frequentes` — for tricky or counter-intuitive behavior

**Depth requirements:**
- Every public class and function introduced in the diff must be explained.
- Every Pydantic field must appear in a table with: field name, type, constraint/default, explanation.
- Every `@field_validator` must explain what rule it enforces and **why** (the reason, not just the mechanics).
- Factory functions (closures) must show the full closure chain: outer → inner → what the inner captures.
- Routing/conditional logic must include an ASCII diagram of the control flow.
- Design decisions that are non-obvious must have a "Porque e assim?" paragraph.

**Language:**
- Prose: Portuguese.
- Code, variable names, comments inside code blocks: English.
- Section headings: Portuguese.

### Step 5 — Add Related Notes (REQUIRED)

Every doc must end with `## Related Notes`. This is critical for Obsidian graph/backlink navigation:

```markdown
## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/NOTE-HUB|Hub Note]]
```

**Rules:**
- Prefer `[[wikilinks]]` for vault notes.
- Use explicit Markdown only when ambiguous (e.g., multiple `README.md`).
- Link 3-5 nearby notes, especially hub notes.
- Always include Docs Home for Epics subfolder notes.

### Step 6 — Write the file

Write the doc with the Write tool to the resolved path.

### Step 7 — Update the vault index

The documentation index is `docs/README.md`. Add one line under the appropriate Epics section:
```
| [US-XXX SLUG](Epics/Epic%20Folder/US-XXX-SLUG-EXPLAINED.md) | short description |
```

### Step 8 — Report to the user

Print:
- The full path of the file written.
- A one-line summary of what the doc covers.
- If any section was omitted (e.g., no Go reference because the code is new), state why.

---

## Quality checklist (verify before writing)

- [ ] Every file in the diff has at least one section.
- [ ] Every code block contains the **actual** code, not a paraphrase.
- [ ] Every Pydantic model has a field table.
- [ ] No section uses vague phrases like "this function processes data" — be specific.
- [ ] ASCII diagrams used for flows with 2+ branches.
- [ ] `---` divider between every top-level section.
- [ ] Frontmatter tag is valid (check `references/doc-pattern.md` for valid tags).
- [ ] File saved to the correct `docs/Epics/<Epic>/` folder.
- [ ] Closing `## Related Notes` uses `[[wikilinks]]`, not `**bold**` (REQUIRED).
- [ ] Docs Home link included for notes in Epics subfolders.
