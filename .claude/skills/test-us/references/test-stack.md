# Test Stack

Required packages, imports, and configuration for the lusitai-aipentest test suite.

---

## Packages

Add to `pyproject.toml` under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "pytest-mock>=3.14",
    "pytest-timeout>=2.3",
    "testcontainers[postgres]>=4.0",
    "polyfactory>=2.16",
    "respx>=0.21",
    "freezegun>=1.4",
    "httpx>=0.27",
]
```

## Package purposes

| Package | Layer | Purpose |
|---|---|---|
| `pytest` | All | Test runner |
| `pytest-asyncio` | All | Async test support (`async def test_...`) |
| `pytest-cov` | All | Coverage reporting (`--cov=src/pentest`) |
| `pytest-mock` | All | `mocker` fixture for patching |
| `pytest-timeout` | Integration, E2E | Prevent hung tests |
| `testcontainers` | Integration | Real PostgreSQL+pgvector in Docker |
| `polyfactory` | Unit | Generate fake Pydantic model instances |
| `respx` | Unit (recon), Agent | Mock HTTP responses: recon detectors (HTML/JS/headers) and LLM API calls |
| `freezegun` | Unit | Mock `datetime.now()` for time-dependent logic |
| `httpx` | Agent, E2E | Async HTTP client for API testing |

## Running tests

```bash
# All unit tests (fast, no deps)
pytest tests/unit/ -v

# Integration tests (needs Docker running)
pytest tests/integration/ -v -m integration

# Agent tests (mocked LLM)
pytest tests/agent/ -v -m agent

# E2E tests (manual, needs API keys + Docker)
pytest tests/e2e/ -v -m e2e

# Everything except E2E
pytest tests/ -v --ignore=tests/e2e/

# With coverage
pytest tests/ --ignore=tests/e2e/ --cov=src/pentest --cov-report=term-missing
```

## Directory structure

```
tests/
    __init__.py
    conftest.py              # Common fixtures, marker registration
    unit/
        __init__.py
        conftest.py          # Unit-specific fixtures (factories)
        test_models.py
        tools/
            test_registry.py
            test_filter.py
            test_args.py
        test_templates.py
        providers/
            test_config.py
        docker/
            test_ports.py
    integration/
        __init__.py
        conftest.py          # DB fixtures (testcontainers), Docker fixtures
        database/
            test_models.py
            test_queries.py
            test_migrations.py
        docker/
            test_client.py
            test_exec.py
            test_files.py
    agent/
        __init__.py
        conftest.py          # Mock LLM fixtures, sample findings
        test_generator.py
        test_orchestrator.py
        test_scanner.py
        test_reporter.py
        test_reflector.py
        test_adviser.py
        test_chain.py
    e2e/
        __init__.py
        conftest.py          # Real LLM fixtures, test target config
        test_full_scan.py
        test_mcp_flow.py
```
