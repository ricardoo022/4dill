---
name: create-pr
description: |
  Creates a pull request for the LusitAI aipentest project following the project's
  PR template and git workflow conventions. Use when asked to "create a PR", "open a PR",
  "make a pull request", "push and create PR", or when implementation work is complete
  and ready to submit for review. Handles branch detection, diff analysis, PR body
  generation from the project template, and `gh pr create` execution.
---

# Create PR

## Overview

Generates and submits a pull request that conforms to the LusitAI aipentest project's
PR template, branch naming conventions, and CI rules. Reads the current branch to
identify the User Story, analyzes the diff to auto-fill the Changes and Tests sections,
and executes `gh pr create` with a properly formatted body.

## Workflow

Execute the phases below in order.

---

### Phase 1 — Detect Branch and User Story

Get the current branch name:

```bash
git branch --show-current
```

Extract the User Story ID from the branch name (pattern: `feature/US-XXX-...`).
If the branch does not follow the naming convention, ask the user for the US number.

Verify there is an open PR for this branch already:

```bash
gh pr list --head "<branch-name>" --json number,state --jq '.[0]'
```

If an open PR already exists, inform the user and stop — do not create a duplicate.

---

### Phase 2 — Analyze the Diff

Get the diff stats against `main`:

```bash
git diff --stat origin/main...HEAD
```

Get the list of changed files:

```bash
git diff --name-only origin/main...HEAD
```

Categorize the changes:
- **Source files** — files under `src/` (implementation changes)
- **Test files** — files under `tests/` (note which layers: unit, integration, agent, e2e)
- **Docs** — files under `docs/` or `*.md` files
- **Database** — files under `alembic/` or `database/` (note if a new migration was added)
- **Config/CI** — files under `.github/`, `pyproject.toml`, `.devcontainer/`, etc.
- **Skills/Agents** — files under `.claude/skills/` or `.claude/agents/`

---

### Phase 3 — Read the User Story

Extract the US number from the branch name (pattern: `US-\d+`).

Read the User Story block from the docs:

```bash
grep -n "### <US_ID>:" docs/USER-STORIES.md
```

Use the line number returned to read from that line onwards:

```bash
# Use Read tool with offset=<line> limit=90 on docs/USER-STORIES.md
```

From the User Story, extract:
- **Title** — the US title text (used in the PR header)
- **Acceptance Criteria** — to verify coverage in the checklist
- **Tests Required** — to verify test completeness

---

### Phase 4 — Build the PR Body

Construct the PR body using the project's PR template (`.github/pull_request_template.md`):

```markdown
## User Story

US-XXX: {title from USER-STORIES.md}

## Summary

- {concise description of what changed and why, derived from the diff}

## Changes

- [ ] {change 1: file or module affected}
- [ ] {change 2}
- [ ] {change N}

## Tests

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated (if DB/Docker involved)
- [ ] Agent tests added/updated (if agent behavior changed)
- [ ] All existing tests pass locally

## Checklist

- [ ] Code follows project conventions (English code, async-first)
- [ ] No secrets or credentials in code
- [ ] Acceptance criteria from US are covered by tests
- [ ] Ran `ruff check` and `ruff format` locally
- [ ] Alembic migration added (if DB schema changed)
- [ ] Docs updated in `docs/` (if new module or pattern added)
```

**Auto-fill rules:**

| Template section | How to populate |
|---|---|
| `US-XXX: {title}` | Extract from `docs/USER-STORIES.md` using the US ID from the branch |
| `## Summary` | 1-2 bullet points summarizing the diff's purpose |
| `## Changes` | One checkbox per file or logical group of files changed |
| `## Tests` | Pre-check items that apply: unit always, integration if `tests/integration/` changed, agent if `tests/agent/` changed, e2e if `tests/e2e/` changed |
| `Alembic migration` | Pre-check if any file under `alembic/versions/` was added |
| `Docs updated` | Pre-check if any file under `docs/` was added |

---

### Phase 5 — Run Pre-PR Checks

Before creating the PR, run these checks and report results:

```bash
ruff check src/ tests/ 2>&1 | tail -20
```

```bash
ruff format --check src/ tests/ 2>&1 | tail -20
```

If lint or format checks fail, fix the issues before proceeding (or ask the user).

---

### Phase 6 — Create the PR

Push the branch and create the PR:

```bash
git push -u origin <branch-name>
```

```bash
gh pr create --base main --title "<PR title>" --body "$(cat <<'EOF'
{PR body from Phase 4}
EOF
)"
```

**PR title format:** Follow the branch convention — use the commit message style:

```
feat(US-XXX): short description
```

or for non-feature changes:

```
fix(US-XXX): short description
chore(US-XXX): short description
test(US-XXX): short description
docs(US-XXX): short description
```

After creation, report the PR URL to the user.
