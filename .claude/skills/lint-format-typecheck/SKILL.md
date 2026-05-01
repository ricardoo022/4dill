---
name: lint-format-typecheck
description: Run ruff lint, ruff format, and mypy type checking on Python projects following CI/CD standards. Executes all three linters sequentially, parses output, and provides a comprehensive quality report with actionable fixes.
---

# Python Lint, Format & Type Check Skill

## Purpose

To automate Python code quality checks using industry-standard tools (ruff, mypy) following the project's CI/CD workflow. This skill ensures consistent code style, catches logical errors, and maintains type safety before code review.

## When to Use This Skill

Invoke this skill when:

- Running pre-commit quality checks (`/lint-format-typecheck`)
- Fixing code quality issues before pushing to remote
- Checking a branch passes all linting and type checks
- Integrating linting into a development workflow
- Generating a comprehensive code quality report

Example triggers:
- "Lint and type-check the code"
- "Run ruff and mypy on this project"
- "Check code quality before PR"
- "Fix formatting and lint issues"

## How to Use This Skill

### Phase 1: Understand the Project Layout

Determine the Python source structure:

1. Identify the `src/` directory (or project source root)
2. Identify the `tests/` directory (or test root)
3. Check for `pyproject.toml` to understand ruff/mypy configuration
4. Check for `src/pentest/` as the main package (or other package name)

### Phase 2: Run Linting in CI/CD Order

Execute the three tools in this exact sequence (matching `.github/workflows/ci.yml`):

**Step 1: Ruff check (linting)**

```bash
ruff check src/ tests/
```

This identifies:
- Import sorting issues
- Unused variables
- Naming convention violations
- Logical errors (unused loops, unreachable code)
- Code complexity issues

If failures: fix them and re-run before proceeding to Step 2.

**Step 2: Ruff format (code formatting)**

```bash
ruff format --check src/ tests/
```

This validates code formatting without making changes. Add `--diff` to see what would be fixed:

```bash
ruff format --diff src/ tests/
```

If failures: apply fixes with:

```bash
ruff format src/ tests/
```

Then re-run the check.

**Step 3: Mypy type checking**

```bash
mypy src/pentest/ --ignore-missing-imports
```

This checks:
- Type annotations correctness
- Type mismatches in function calls
- Missing return type annotations
- Protocol violations

Note: Only checks `src/pentest/` (the main package), not tests.

### Phase 3: Parse Output and Report

After running all three tools, generate a summary report:

```
## Code Quality Report

### Ruff Check
- Status: ✅ PASS | ❌ FAIL
- Issues: {count}
- Top issues: {issue list}

### Ruff Format
- Status: ✅ PASS | ❌ FAIL
- Files needing format: {count}

### Mypy Type Check
- Status: ✅ PASS | ❌ FAIL
- Type errors: {count}
- Error summary: {types of errors}

### Summary
- Overall: ✅ ALL PASS | ❌ {tool} FAILED
- Next: {concrete fix or "Ready for PR"}
```

### Phase 4: Apply Fixes

If issues are found, apply fixes in this order:

1. **Ruff check fixes** — auto-fixable issues:
   ```bash
   ruff check --fix src/ tests/
   ```

2. **Ruff format** — always safe:
   ```bash
   ruff format src/ tests/
   ```

3. **Mypy errors** — manual fixes required
   - Read error message
   - Add missing type annotations
   - Fix type mismatches in code
   - Re-run `mypy src/pentest/ --ignore-missing-imports`

### Phase 5: Verify Clean State

After fixes, re-run all three checks:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/pentest/ --ignore-missing-imports
```

All should pass (exit code 0).

## Configuration Reference

Project configuration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]
ignore = ["E501"]  # Line length enforced by formatter, not linter

[tool.mypy]
ignore_missing_imports = true
```

## Real-World Workflow Example

```bash
# 1. Check current state
ruff check src/ tests/  # ❌ 5 issues
ruff format --check src/ tests/  # ❌ 3 files need formatting
mypy src/pentest/ --ignore-missing-imports  # ❌ 2 type errors

# 2. Auto-fix ruff issues
ruff check --fix src/ tests/  # ✅ Fixed 4, 1 requires manual fix

# 3. Format all code
ruff format src/ tests/  # ✅ Formatted 3 files

# 4. Fix type errors manually
# Edit src/pentest/models/flow.py - add missing return type
# Edit src/pentest/tools/terminal.py - fix argument type mismatch

# 5. Re-check all
ruff check src/ tests/  # ✅ PASS
ruff format --check src/ tests/  # ✅ PASS
mypy src/pentest/ --ignore-missing-imports  # ✅ PASS

# 6. Ready for commit
git add .
git commit -m "fix: lint and format code before PR"
git push
```

## Troubleshooting

### Issue: "ruff: command not found"

**Fix:** Install dev dependencies:
```bash
pip install -e ".[dev]"
```

### Issue: Ruff reports "line too long" even with ruff format

**Fix:** Check `pyproject.toml` — `line-length` might be different from default. Also check `[tool.ruff.lint]` for conflicting rules.

### Issue: Mypy reports many "error: Skipping analyzing..." messages

**Fix:** This is normal with `--ignore-missing-imports`. It means the stub is missing. If critical, add the package to a typing stub or fix the import.

### Issue: Fix applied but check still fails

**Fix:** Some issues require manual intervention:
1. **Ruff check** has non-auto-fixable rules (e.g., naming violations)
2. **Mypy** always requires manual type fixes
3. Re-read the error message and fix manually, then re-check

## Related Documentation

- `.github/workflows/ci.yml` — CI/CD pipeline that runs these checks
- `pyproject.toml` — Ruff and mypy configuration
- `CLAUDE.md` — Project linting conventions
