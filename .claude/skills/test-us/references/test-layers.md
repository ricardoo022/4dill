# Test Layers

Four testing layers for the lusitai-aipentest engine. Every test belongs to exactly one layer.

**Priority rule: integration > agent > unit > e2e.**
Never put a test in a lower layer when real infrastructure (DB, Docker, HTTP) is available to exercise it.
`tests/e2e/` is for full scan flows only — individual US behavior belongs in `tests/integration/` or `tests/agent/`.

---

## Layer 1: Unit Tests

**Directory:** `tests/unit/`
**Dependencies:** None (no DB, no Docker, no network)
**Speed:** Fast (milliseconds)
**Runs in CI:** Always

### What belongs here

- Pydantic model validation (serialization, enums, constraints)
- Pure functions (parsing, formatting, filtering)
- Command filter logic (destructive command detection)
- Template rendering (Jinja2 output correctness)
- Config loading and validation
- Argument parsing for tools
- Tool registry completeness
- Port allocation formulas
- CRC32 hostname generation
- Logic that has no infrastructure to exercise — if there is a real DB, Docker, or HTTP call to make, use integration instead

### Module mapping

| Source module | Test file pattern |
|---|---|
| `src/pentest/models/` | `tests/unit/test_models.py` |
| `src/pentest/tools/registry.py` | `tests/unit/tools/test_registry.py` |
| `src/pentest/tools/filter.py` | `tests/unit/tools/test_filter.py` |
| `src/pentest/tools/args.py` | `tests/unit/tools/test_args.py` |
| `src/pentest/templates/` | `tests/unit/test_templates.py` |
| `src/pentest/providers/config.py` | `tests/unit/providers/test_config.py` |
| `src/pentest/docker/ports.py` | `tests/unit/docker/test_ports.py` |
| `src/pentest/recon/supabase.py` | `tests/unit/recon/test_supabase.py` |
| `src/pentest/recon/firebase.py` | `tests/unit/recon/test_firebase.py` |
| `src/pentest/recon/custom_api.py` | `tests/unit/recon/test_custom_api.py` |
| `src/pentest/recon/subdomains.py` | `tests/unit/recon/test_subdomains.py` |
| `src/pentest/recon/orchestrator.py` | `tests/unit/recon/test_orchestrator.py` |
| `src/pentest/tools/terminal.py` | `tests/unit/tools/test_terminal_file.py` |
| `src/pentest/tools/file.py` | `tests/unit/tools/test_terminal_file.py` |

### Characteristics

- No I/O, no network, no filesystem side effects
- Use `polyfactory` to generate fake Pydantic instances
- Use `pytest.mark.parametrize` for table-driven tests
- Test both valid and invalid inputs
- **Recon detectors** use `respx` to mock HTTP with realistic HTML/JS/headers that exercise actual regex patterns (real HTTP mocks, not trivial `"ok"` strings — see `real-data-fixtures.md`)
- **Tool factories** use `MagicMock` with realistic command outputs (nmap results, file contents), not trivial strings
- Use realistic domain data even in unit tests: CVEs, ports, hostnames, model names

---

## Layer 2: Integration Tests ← PRIMARY LAYER FOR MOST US

**Directory:** `tests/integration/`
**Dependencies:** Real PostgreSQL (testcontainers), real Docker daemon
**Speed:** Moderate (seconds to low minutes)
**Runs in CI:** Always (with services available)
**Marker:** `@pytest.mark.integration`

### What belongs here

**This is the default layer for any US that touches real infrastructure.**
If in doubt between unit and integration: use integration.
If in doubt between integration and e2e: use integration.

- SQLAlchemy model CRUD (create, read, update, delete)
- Alembic migrations (upgrade, downgrade, idempotency)
- pgvector similarity search with real vectors
- Docker container lifecycle (create, exec, file ops, stop, remove)
- Database query functions
- Foreign key cascades and trigger verification
- Index verification
- Vector extension creation
- Tool execution against real Docker containers (terminal, file)
- Graphiti/Neo4j round-trips (add_messages → search)
- DuckDuckGo / Tavily search tool round-trips (real HTTP)
- **Round-trip proof tests for every US that stores or retrieves data** (mandatory)

### Module mapping

| Source module | Test file pattern |
|---|---|
| `src/pentest/database/models.py` | `tests/integration/database/test_models.py` |
| `src/pentest/database/queries/` | `tests/integration/database/test_queries.py` |
| `src/pentest/docker/client.py` | `tests/integration/docker/test_client.py` |
| `src/pentest/docker/exec.py` | `tests/integration/docker/test_exec.py` |
| `src/pentest/docker/files.py` | `tests/integration/docker/test_files.py` |
| `alembic/versions/` | `tests/integration/database/test_migrations.py` |
| `src/pentest/tools/terminal.py` | `tests/integration/tools/test_terminal.py` |
| `src/pentest/tools/file.py` | `tests/integration/tools/test_file.py` |
| `src/pentest/graphiti/client.py` | `tests/integration/graphiti/test_client.py` |
| `src/pentest/tools/duckduckgo.py` | `tests/integration/tools/test_duckduckgo_integration.py` |
| `src/pentest/tools/tavily.py` | `tests/integration/tools/test_tavily_integration.py` |

### Characteristics

- Use `testcontainers` for PostgreSQL (spins up real DB in Docker)
- Use real Docker daemon for container tests
- Each test gets a fresh database (transaction rollback or session-scoped recreate)
- Async tests with `pytest-asyncio` (`asyncio_mode = "auto"`)
- Cleanup after each test (remove containers, rollback transactions)
- **Round-trip proof tests always assert the retrieved data matches what was inserted** — never `pytest.skip()` when the assertion fails; fail loudly so infrastructure problems are visible
- Assertions must check specific field values, not just `assert result is not None`
- Use `pytest.mark.integration` on every test in this layer

---

## Layer 3: Agent Tests

**Directory:** `tests/agent/`
**Dependencies:** Mocked LLM responses; real or mocked DB/Docker for tool execution
**Speed:** Moderate (seconds)
**Marker:** `@pytest.mark.agent`
**Runs in CI:** Always

### What belongs here

- Agent receives input and calls expected tools in correct sequence
- Agent delegation (Orchestrator delegates to Scanner, not Coder, for security tests)
- Reflector corrects agent that returns text without tool calls
- Adviser intervenes after 20+ repeated tool calls
- Reporter produces valid ScanReport JSON from findings
- Generator creates plan with ≤ 15 subtasks
- Refiner adjusts plan based on completed subtask results
- Barrier tools terminate agent loop correctly
- Context passing between agents (filtered, not full dump)
- Loop detection (5+ same tool calls → abort)

### Characteristics

- Mock the LLM only: return predefined `AIMessage` tool_calls for given inputs
- Use realistic tool call sequences — real commands, real paths, real output content (see `real-data-fixtures.md`)
- Where possible, execute tools against real Docker/DB rather than mocking them too
- Validate tool call sequence, not just final output
- Test loop detection (5+ same tool = abort), recursion limit, and barrier extraction
- Use `@pytest.mark.agent` on every test in this layer

---

## Layer 4: E2E Tests

**Directory:** `tests/e2e/`
**Dependencies:** Real LLM API, real Docker, real DB, live test target
**Speed:** Slow (minutes)
**Marker:** `@pytest.mark.e2e`
**Runs in CI:** Never (manual only — expensive, requires API keys)

### What belongs here

**ONLY full scan flows belong in e2e.** Do not put individual US behavior here.
If a test can run without a real LLM API call, it does not belong in e2e.

- Complete scan against a test target (OWASP Juice Shop, local vulnerable app)
- MCP server request → Generator plan → Orchestrator loop → Scanner exec → Reporter final ScanReport JSON
- Docker container spins up, tools execute, findings are produced
- Reporter validates and produces correct output format

### Module mapping

| Source module | Test file pattern |
|---|---|
| `src/pentest/controller/flow.py` | `tests/e2e/test_full_scan.py` |
| `src/pentest/mcp/server.py` | `tests/e2e/test_mcp_flow.py` |

### Characteristics

- Run manually: `pytest tests/e2e/ -m e2e`
- Require real API keys (`ANTHROPIC_API_KEY`)
- Use a known test target with predictable vulnerabilities
- Validate final `ScanReport` against Pydantic schema
- Long timeouts (10+ minutes per test)
- Never run in CI — too slow, too expensive
