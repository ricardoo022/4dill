---
name: approve-pr
description: |
  Full PR review cycle for the LusitAI aipentest project. Given a PR number (or the
  current branch), this skill fetches the diff, identifies the User Story being
  implemented, reads the acceptance criteria and required tests from USER-STORIES.md,
  routes framework-specific judgment through official LangChain/LangGraph/Deep Agents
  skills using docs/LANGCHAIN-SKILLS-GUIDE.md as routing source of truth,
  enforces validation with real infrastructure tests (integration/agent/e2e) whenever
  the story impacts runtime behavior, rejects mock-only evidence for behavior that can
  be tested with Docker/PostgreSQL/Neo4j/real HTTP, runs a pre-landing code quality
  review (SQL safety, LLM trust boundary, shell injection, async/sync mixing, and
  more), reads every changed source file, and issues a structured APPROVE / REQUEST
  CHANGES verdict. Use when asked to
  "review this PR", "aprovar PR", "analisar PR", "check this PR", or "dar veredicto do PR".
---

# Approve PR

## Overview

End-to-end PR review tailored to this project's conventions. Covers: diff analysis,
User Story traceability, test execution, architecture coherence, and a final APPROVE /
REQUEST CHANGES verdict with actionable inline comments.

When the PR touches LangChain/LangGraph/Deep Agents concerns, invoke the corresponding
official skill(s) to support technical judgment instead of relying only on generic review.

## Argument

The skill accepts an optional PR number in the invocation arguments (e.g. `/approve-pr 42`).

- If a number was provided, use it as `PR_NUM`.
- Otherwise, detect it from the current branch with the bash block in Phase 1.

Do NOT run bash to extract the argument — read it from the invocation text directly.

---

## Workflow

Execute the seven phases below in order. Collect evidence at each phase; synthesise into
the verdict only at the end.

Apply this non-negotiable rule during all phases:
- Prefer real-evidence validation over synthetic validation.
- Treat mock-only tests as insufficient when the behavior can be validated with available real infrastructure.
- Allow mocks only when real validation is not technically feasible in CI/devcontainer and record explicit justification.

---

### Phase 1 — Fetch the PR

If `PR_NUM` was not provided as an argument, detect it:

```bash
git branch --show-current
```

Then look up the open PR for that branch:

```bash
gh pr list --head "<branch-name>" --json number,title,baseRefName,headRefName --jq '.[0]'
```

Once `PR_NUM` is known, fetch metadata and diff stats:

```bash
gh pr view <PR_NUM> --json title,body,baseRefName,headRefName,author,state,labels,reviewDecision
```

```bash
gh pr diff <PR_NUM> --stat
```

For the full diff, fetch it and read carefully. If the diff is very large (>300 lines),
fetch only the file list first and read each file individually in Phase 3 instead:

```bash
gh pr diff <PR_NUM> --name-only
```

```bash
gh pr diff <PR_NUM>
```

Note from the diff:
- Which files changed and why
- The branch name encodes the User Story ID (e.g. `feature/US-055-...` → `US-055`)

---

### Phase 2 — Read the User Story

Extract the US number from the branch name or PR title (pattern: `US-\d+`).

Then read the User Story block from the docs:

```bash
grep -n "### <US_ID>:" docs/USER-STORIES.md
```

Use the line number returned to read from that line onwards (approximately 80 lines):

```bash
# Use Read tool with offset=<line> limit=90 on docs/USER-STORIES.md
```

From the User Story, extract and record:
- **Acceptance Criteria** — every checklist item that must be satisfied
- **Tests Required** — the specific test scenarios that must exist and pass
- **Technical Notes** — implementation constraints

---

### Phase 2.5 — Route to LangChain/LangGraph Skills (When Applicable)

Before evaluating architecture or tests in depth, decide whether specialized framework
skills are required. Use `docs/LANGCHAIN-SKILLS-GUIDE.md` as the routing source of truth.

Execute this routing checklist:

1. Read changed files and PR scope signals (paths, symbols, behavior changed).
2. Match detected scope to the guide's "Quando" and "No projecto" sections.
3. Invoke the relevant skill(s) and incorporate their guidance into later phases.
4. Record in review notes which skill(s) were invoked and why.

Routing matrix (derived from `docs/LANGCHAIN-SKILLS-GUIDE.md`):

- Invoke `/langgraph-fundamentals` when PR changes `StateGraph`, graph nodes/edges,
  routing loops, `Command`, `Send`, streaming, or agent-chain orchestration.
- Invoke `/langchain-fundamentals` when PR changes `create_agent()`, `@tool`, tool
  binding, agent construction, or tool interface contracts.
- Invoke `/langgraph-persistence` when PR changes checkpointers, `thread_id`, state
  recovery, Store usage, or persistence boundaries.
- Invoke `/langchain-middleware` when PR changes tool interception, reflection/retry,
  human approval middleware, or structured output middleware.
- Invoke `/langgraph-human-in-the-loop` when PR changes `interrupt()`,
  `Command(resume=...)`, barrier pause/resume flows, or approval/validation flows.
- Invoke `/langchain-rag` when PR changes embeddings, retrievers, vector stores,
  Memorist behavior, semantic memory tools, or ingestion/index pipelines.
- Invoke `/deep-agents-orchestration` when PR changes subagent delegation, planning,
  or task decomposition middleware.
- Invoke `/deep-agents-memory` when PR changes StateBackend/StoreBackend/Composite
  backend logic or filesystem-memory routing.
- Invoke `/deep-agents-core` when PR introduces or refactors `create_deep_agent()`
  harness-level behavior.
- Invoke `/framework-selection` only when PR proposes changing framework layer choices
  (LangChain vs LangGraph vs Deep Agents).
- Invoke `/langchain-dependencies` when PR changes framework dependency versions,
  provider packages, or installation/setup constraints.

Invocation policy:

- Invoke no framework skill only when PR does not touch these concerns (document why N/A).
- Invoke multiple skills when scope crosses boundaries (e.g., graph + middleware + persistence).
- Treat missing required invocation as a review quality gap; fix it before issuing verdict.

---

### Phase 3 — Read Changed Source Files

List the changed files, split by category:

```bash
gh pr diff <PR_NUM> --name-only
```

For each file that is **not** under `tests/` and **not** under `docs/`, use the Read tool
to read it in full. Do not skip any source file.

For each file, evaluate:
- Does it follow the existing module pattern described in CLAUDE.md §Module Responsibilities?
- Is async used consistently (`async def`, `await`, `AsyncSession`)?
- Are Pydantic v2 models used for all data structures at boundaries?
- New tools: do they use factory closures matching `tools/terminal.py` or `tools/browser.py`?
- New barriers: are they registered in `BarrierAwareToolNode` and do they extract the right args?
- New Jinja2 templates: are they in `src/pentest/templates/prompts/` with `.md.j2` extension? Does the renderer set `template_dir = Path(__file__).parent / "prompts"` and call `env.get_template("name.md.j2")`?
- No REST endpoints — external interface is MCP only
- Doc files must have Obsidian frontmatter `tags: [...]`

#### README.md Co-Change Check

For every changed file, check whether a `README.md` exists in the same directory:

```bash
# For each changed file, get its directory and check for README.md
```

If a `README.md` exists in the same directory as a changed source or test file, verify that
the `README.md` is also included in this PR's changes. The README should be updated to
reflect the modifications made to the sibling file (new features, changed behavior, updated
usage examples, etc.).

If a changed file has a sibling `README.md` that was **not** modified in this PR, record
this as a finding under the verdict with the file path and a description of what the README
likely needs to be updated for.

---

### Phase 4 — Read and Run Tests

First, list test files changed or added in this PR:

```bash
gh pr diff <PR_NUM> --name-only | grep '^tests/'
```

Use the Read tool to read each test file. Verify:
- Tests cover each item in the User Story's **Tests Required** list
- Tests are in the correct layer (unit / integration / agent / e2e) per CLAUDE.md §Testing Strategy
- No `@pytest.mark.asyncio` decorators — `asyncio_mode = "auto"` is already configured
- Mocks/fixtures follow existing patterns (polyfactory, respx, testcontainers)

#### Real-Evidence Testing Requirement (Blocking)

Validate User Story behavior with the deepest practical layer using real dependencies:
- Prefer `tests/integration/` and `tests/e2e/` for runtime behavior.
- Use real PostgreSQL, real Docker containers, real Neo4j/Graphiti, and real HTTP services whenever relevant.
- Treat unit tests with mocks as supplemental only, not primary evidence, for behavior that crosses process/network/storage boundaries.
- If a PR includes only mocked tests for behavior that can be validated with real infrastructure, record a **blocking** finding.

Allow mock-only testing only when both conditions are true:
- Real infra validation is genuinely unavailable or would be non-deterministic in this repository context.
- The review includes a written justification plus a concrete follow-up test plan (which layer/file will be added later).

#### E2E Test Requirement

Determine whether the PR changes introduce functionality that should be validated end-to-end.
A PR **must** include e2e tests (under `tests/e2e/`) when:
- It adds or modifies an agent's execution graph or tool set
- It introduces a new scan phase or workflow step
- It changes the controller flow (task lifecycle, subtask delegation)
- It modifies how tools interact with external systems (Docker, PostgreSQL, Neo4j, MCP)
- It adds new user-facing behavior that is testable via a full scan round-trip

For PRs that only touch documentation, configuration, refactoring without behavioral change,
or purely internal helpers, e2e tests may be marked N/A with justification.

If e2e tests are required but missing, record this as a **blocking** finding in the verdict.
If e2e tests exist, verify:
- They are marked with `@pytest.mark.e2e`
- They exercise a real round-trip (real LLM when applicable, real Docker, real target or deterministic real test fixture)
- They assert end-state correctness (DB records, scan outputs, knowledge graph entries)

Then run the tests. Run only the files that are part of this PR first:

```bash
pytest <test-file-1> <test-file-2> -v --tb=short 2>&1 | tail -80
```

If they pass, run the full suite for each affected layer to catch regressions:

```bash
pytest tests/unit/ -v --tb=short -q 2>&1 | tail -40
```

Run integration and agent layers only if files under those paths changed:

```bash
pytest tests/integration/ -v -m integration --tb=short -q 2>&1 | tail -40
pytest tests/agent/ -v -m agent --tb=short -q 2>&1 | tail -40
```

When PR touches runtime flow/agents/tools/database/docker/mcp boundaries, run affected integration tests even if test files were not edited, because existing real-data tests may still detect regressions.

---

### Phase 5 — Code Quality Review

Read `references/code-review-checklist.md` and apply it to the diff obtained in Phase 1.

Before finalizing findings, merge insights gathered from Phase 2.5 skill invocations.
If a specialized skill recommends stricter validation than the default checklist,
apply the stricter rule.

Run **Pass 1 (CRITICAL)** first, then **Pass 2 (INFORMATIONAL)**. For each finding:
- Record the file, line number, category, and a one-line description.
- Classify as `AUTO-FIX` or `ASK` using the Fix-First heuristic in the checklist.
- Apply `AUTO-FIX` items immediately with the Edit tool.
- Batch `ASK` items — do not interrupt the review flow.

Skip categories that clearly don't apply to this diff (e.g., View/Frontend if no frontend
files changed, Distribution/CI-CD if no workflow files changed).

---

### Phase 6 — Architecture Coherence Check

Run lint and type checks:

```bash
ruff check src/ tests/ 2>&1 | tail -30
```

```bash
mypy src/pentest/ --ignore-missing-imports 2>&1 | tail -30
```

Then fill in this table based on what was observed in Phases 3 and 4:

| # | Check | Result |
|---|-------|--------|
| 1 | All new async functions use `async def` and are awaited correctly | |
| 2 | New DB queries use `AsyncSession` and the existing session context manager | |
| 3 | New Pydantic models use v2 syntax (`model_config`, `Field`, no `__validators__`) | |
| 4 | New tools use factory closures matching `tools/terminal.py` or `tools/browser.py` | |
| 5 | New barriers registered in `BarrierAwareToolNode` and extract the right args | |
| 6 | No direct `requests` / sync HTTP calls — only `httpx.AsyncClient` | |
| 7 | Imports follow project structure (no circular, no star imports) | |
| 8 | `ruff check` passes with no new errors | |
| 9 | `mypy` passes with no new errors | |
| 10 | Doc files (if any) have correct Obsidian frontmatter tags | |
| 11 | Changed files with sibling `README.md` include a README update in this PR | |
| 12 | E2E tests included when PR introduces user-facing or end-to-end testable behavior | |
| 13 | New Jinja2 templates are in `templates/prompts/` with `.md.j2` extension; renderer uses `Path(__file__).parent / "prompts"` as `template_dir` | |

Use YES / NO / N/A for each row, with a one-line justification.

---

### Phase 6.5 — Update User Story (If Approved)

If the verdict will be APPROVE, update the USER-STORIES.md file to mark the User Story as complete:

1. Find the US section in `docs/USER-STORIES.md` (e.g., `### US-055: Description`)
2. Add `(DONE)` to the section title if not already present: `### US-055: Description (DONE)`
3. For each checkbox under **Acceptance Criteria**, change `- [ ]` to `- [x]` (all must be checked)
4. For each checkbox under **Tests Required**, change `- [ ]` to `- [x]` (all must be checked)
5. For each checkbox under **Definition of Done**, change `- [ ]` to `- [x]` (all must be checked)

Use the Edit tool to make these changes. If any criteria or tests are already checked, preserve them.

---

### Phase 7 — Verdict

Produce the following structured report:

#### Summary

One paragraph: what this PR implements, which US it closes, overall quality impression.

Include which LangChain/LangGraph/Deep Agents skills were invoked (if any) and why.

#### Acceptance Criteria Coverage

For each criterion from the User Story:
- ✅ Met
- ❌ Not Met — quote the specific missing piece
- ⚠️ Partial — quote what is missing

#### Test Coverage

For each item in **Tests Required**:
- ✅ Exists and passes
- ❌ Missing
- ⚠️ Exists but fails — include the failure output

Also classify evidence quality per item:
- `REAL` — validated with real infrastructure/dependencies
- `MOCKED` — validated only with stubs/mocks/fakes

Any required runtime behavior marked only as `MOCKED` must be treated as blocking unless explicitly justified as infeasible.

#### Code Quality Review

Summary of Phase 5 findings. Format:

```
Pre-Landing Review: N issues (X critical, Y informational)

AUTO-FIXED:
- [file:line] Problem → fix applied

NEEDS INPUT:
- [file:line] Problem description
  Recommended fix: suggested fix
```

If no issues: `Pre-Landing Review: No issues found.`

#### Documentation Updates

For each changed source or test file that has a `README.md` in the same directory, verify
whether the README was updated in this PR. List files that need README updates and describe
what documentation change is expected:

```
README.md co-changes:
- [ ] `src/pentest/foo.py` changed → `src/pentest/README.md` not updated. README should document the new X feature.
```

If all sibling READMEs were properly updated: `Documentation Updates: All README files updated.`

#### E2E Test Coverage

State whether e2e tests are required for this PR and whether they were provided:

```
E2E Tests: Required ✅ / Not Required (justification: ...)
Status: Included ✅ / Missing ❌
```

If included, summarize what scenarios they cover. If missing but required, this is a
blocking issue.

#### Architecture Issues

The completed table from Phase 6. If all YES/N/A: "No issues found."

#### Inline Comments

For any specific line-level concerns:

```
src/pentest/tools/barriers.py:42 — reason or suggestion
```

#### Final Verdict

```
VERDICT: APPROVE
```

or

```
VERDICT: REQUEST CHANGES

Blocking issues:
1. ...

Non-blocking suggestions:
1. ...
```

**APPROVE** requires all of the following:
- Every acceptance criterion is ✅ Met
- Every required test exists and passes
- Required runtime behaviors are validated with REAL evidence (not mock-only)
- E2E tests included when the PR introduces user-facing or end-to-end testable behavior
- Changed files with sibling `README.md` include a README update in this PR
- `ruff` and `mypy` produce no new errors
- No blocking architecture issues
- No CRITICAL findings from the code quality review (Pass 1 of checklist)

When APPROVE is issued, automatically execute Phase 6.5 to mark the User Story as complete in `docs/USER-STORIES.md`:
- Add `(DONE)` to the US title if not present
- Check all acceptance criteria boxes
- Check all test requirement boxes
- Check all definition of done boxes

**REQUEST CHANGES** when any of the above is not satisfied.
