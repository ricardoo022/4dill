# Python Linting & Type Checking Reference

## Tool Comparison

| Tool | Purpose | Scope | Fixable |
|---|---|---|---|
| **ruff check** | Code quality & lint | src/ + tests/ | ~70% auto-fixable |
| **ruff format** | Code formatting | src/ + tests/ | ~100% auto-fixable |
| **mypy** | Type safety | src/pentest/ only | ~20% auto-fixable |

## Common Error Codes

### Ruff Check Errors

| Code | Meaning | Example Fix |
|---|---|---|
| F841 | Unused variable | Remove or use the variable |
| E401 | Multiple imports on one line | Split into separate imports |
| I001 | Import sorting issue | `ruff check --fix` auto-fixes |
| N806 | Variable name should be lowercase | Rename variable |
| W291 | Trailing whitespace | `ruff format` auto-fixes |
| SIM105 | Use contextmanager instead of try/finally | Refactor to use `with` statement |

### Ruff Format Issues

| Issue | Cause | Fix |
|---|---|---|
| Line too long | Code exceeds 100 chars | Refactor or split line |
| Inconsistent spacing | Mixed tabs/spaces | `ruff format` auto-fixes |
| Missing blank lines | Section separation | `ruff format` auto-fixes |

### Mypy Errors

| Error | Meaning | Example Fix |
|---|---|---|
| error: Missing return type | Function missing return annotation | Add `-> ReturnType` to function |
| error: Argument 1 has incompatible type | Type mismatch in call | Cast or convert to correct type |
| error: Name "X" is not defined | Variable not in scope | Import or define before use |
| error: Cannot access member "X" for type "Y" | Attribute doesn't exist | Check type, may need type stub |

## Exit Codes

```
0 = All checks passed
1 = One or more checks failed
```

## Command Reference

### Fast Check (no fixes)

```bash
# Check without making changes
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/pentest/ --ignore-missing-imports
```

### Auto-Fix (safe operations only)

```bash
# Apply auto-fixable issues
ruff check --fix src/ tests/
ruff format src/ tests/
# mypy cannot auto-fix, requires manual changes
```

### Detailed Report

```bash
# Show what would be fixed without applying
ruff format --diff src/ tests/

# Show all ruff issues with line numbers
ruff check --show-settings src/ tests/

# Show mypy errors with context
mypy src/pentest/ --ignore-missing-imports --show-error-context
```

### Single File/Directory

```bash
# Lint specific file
ruff check src/pentest/models/flow.py

# Format specific directory
ruff format src/pentest/tools/

# Type-check specific file
mypy src/pentest/database/models.py --ignore-missing-imports
```

## Configuration Details

### Ruff Config (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
# E = PEP 8 errors
# F = PyFlakes (unused variables, undefined names)
# W = PyFlakes warnings
# I = isort (import sorting)
# N = pep8-naming
# UP = pyupgrade
# B = flake8-bugbear
# A = flake8-builtins
# SIM = flake8-simplify
# TCH = flake8-type-checking
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]

# E501 (line too long) — enforced by formatter, not linter
ignore = ["E501"]
```

### Mypy Config (pyproject.toml)

```toml
[tool.mypy]
ignore_missing_imports = true
# Other options:
# strict = true  # Full type checking
# disallow_untyped_defs = true  # All functions must have types
# warn_return_any = true  # Warn when returning Any
```

## Typical Workflow

1. **Before commit:**
   ```bash
   ruff check --fix src/ tests/
   ruff format src/ tests/
   mypy src/pentest/ --ignore-missing-imports
   ```

2. **If mypy fails:**
   - Read error message
   - Edit source file to add type annotation or fix type mismatch
   - Re-run mypy until all pass

3. **Commit when all pass:**
   ```bash
   git add .
   git commit -m "fix: lint, format, and type-check code"
   git push
   ```

## Performance Tips

- **Sequential order matters:** ruff check → ruff format → mypy (later tools depend on earlier)
- **Cache:** Dependencies are cached in CI, so re-runs are fast
- **Parallel safe:** All three tools can technically run in parallel in CI, but sequential is safer for dependency ordering
- **Scope:** Limiting to `src/` and `tests/` (not docs or config) keeps checks fast

## Integration with IDE

### VS Code

Add to `.vscode/settings.json`:

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit"
    }
  }
}
```

### PyCharm

1. Settings → Tools → Python Integrated Tools → Default Linter → Ruff
2. Settings → Tools → Python Integrated Tools → Default Formatter → Ruff
3. Settings → Tools → Python Integrated Tools → Default Mypy

## Further Reading

- Ruff docs: https://docs.astral.sh/ruff/
- Mypy docs: https://mypy.readthedocs.io/
- PEP 8: https://www.python.org/dev/peps/pep-0008/
