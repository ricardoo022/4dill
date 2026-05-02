# Test Patterns

Concrete pytest patterns for each test layer. Reference when generating test code.

---

## Round-Trip Proof Patterns

Every US that stores, retrieves, or transforms data requires at least one round-trip proof test.
The pattern is always: **insert real data → execute operation → retrieve via real system → assert**.
These are always integration tests — never mocks.

Mark these tests with the `🔁` docstring tag so they are easy to identify.

---

### Docker: ensure_image round-trip

```python
@pytest.mark.integration
def test_ensure_image_round_trip(tmp_path: Path) -> None:
    """🔁 ensure_image pulls image, then images.get confirms it is cached locally."""
    config = DockerConfig(data_dir=str(tmp_path), docker_default_image="debian:latest")
    client = DockerClient(db_session=MagicMock(), config=config)

    resolved = client.ensure_image("alpine:3.20")

    # Round-trip: retrieve directly from Docker daemon to prove it is really there
    image = client._client.images.get(resolved)
    assert image is not None
    assert any("alpine:3.20" in tag for tag in image.tags)
```

### Docker: container exec round-trip

```python
@pytest.mark.integration
async def test_run_container_exec_round_trip(docker_client: DockerClient) -> None:
    """🔁 run_container creates container, exec writes file, file read confirms it is there."""
    container_id = await docker_client.run_container(
        name="test-roundtrip", image="alpine:3.20", flow_id=9999
    )
    try:
        await docker_client.exec_command(container_id, "sh -c 'echo roundtrip > /work/proof.txt'")
        content = await docker_client.read_file(container_id, "/work/proof.txt")
        assert "roundtrip" in content
    finally:
        await docker_client.remove_container(container_id)
```

### Database: insert → query round-trip

```python
@pytest.mark.integration
async def test_create_flow_round_trip(db_session: AsyncSession) -> None:
    """🔁 create_flow persists to DB, get_flows retrieves it back in results."""
    flow = await create_flow(db_session, CreateFlowParams(
        title="scan https://target.local",
        model="claude-sonnet-4-6",
    ))
    assert flow.id is not None

    # Round-trip: query through real DB to prove it was actually persisted
    results = await get_flows(db_session)
    ids = [f.id for f in results]
    assert flow.id in ids

    fetched = await get_flow(db_session, flow.id)
    assert fetched.title == "scan https://target.local"
    assert fetched.status == FlowStatus.CREATED
```

### Database: vector search round-trip (pgvector)

```python
@pytest.mark.integration
async def test_vector_store_round_trip(db_session: AsyncSession) -> None:
    """🔁 store_memory embeds and saves, similarity_search retrieves it back."""
    content = "OpenSSH 7.4 vulnerability CVE-2023-38408 affects port 22"
    await store_memory(db_session, content=content, flow_id=1)

    # Round-trip: search with semantically similar query to prove embedding was saved
    results = await similarity_search(db_session, query="SSH CVE vulnerability port 22", flow_id=1)
    assert len(results) > 0
    assert any("CVE-2023-38408" in r.content or "OpenSSH" in r.content for r in results)
```

### Graphiti: add_message → search round-trip

```python
@pytest.mark.integration
async def test_graphiti_message_round_trip(graphiti_client: GraphitiClient) -> None:
    """🔁 add_messages sends episode, recent_context_search retrieves it back."""
    run_id = uuid4().hex[:8]
    group_id = f"test-roundtrip-{run_id}"
    host = f"target-{run_id}.internal"

    await graphiti_client.add_messages(
        [GraphitiMessage(role="agent", content=f"Host {host} has port 22 open running OpenSSH 8.9")],
        group_id=group_id,
    )

    # Round-trip: search by the host name we just inserted
    # Poll to allow async indexing (with hard timeout — never skip, fail loudly)
    result = None
    for _ in range(12):
        await asyncio.sleep(5)
        result = await graphiti_client.recent_context_search(host, group_ids=[group_id])
        if result.edges or result.nodes:
            break

    assert result is not None and (result.edges or result.nodes), (
        f"Graphiti did not index the episode for group {group_id} after 60s. "
        "Check that the Graphiti worker is running and LLM credentials are valid."
    )
    text = " ".join(e.fact or "" for e in result.edges) + " ".join(n.name or "" for n in result.nodes)
    assert host in text.lower() or "openssh" in text.lower()
```

### Tools: terminal tool output round-trip

```python
@pytest.mark.integration
async def test_terminal_tool_writes_and_reads_file(docker_client: DockerClient) -> None:
    """🔁 terminal tool runs command that writes file, file tool reads it back."""
    container_id = await docker_client.run_container(
        name="test-tools-roundtrip", image="alpine:3.20", flow_id=9998
    )
    terminal = create_terminal_tool(docker_client, container_id)
    file_tool = create_file_tool(docker_client, container_id)
    try:
        # Insert: write data via terminal
        terminal.run({"input": "echo 'CVE-2023-1234 found on port 80' > /work/findings.txt",
                      "cwd": "/work", "timeout": 10, "message": "write findings"})

        # Retrieve: read back via file tool
        content = file_tool.run({"action": "read_file", "path": "/work/findings.txt",
                                 "message": "read findings"})

        assert "CVE-2023-1234" in content
        assert "port 80" in content
    finally:
        await docker_client.remove_container(container_id)
```

### Skills loader: load → lookup round-trip

```python
@pytest.mark.integration
def test_skill_loader_round_trip(skill_index_path: Path) -> None:
    """🔁 load_fase_index parses SKILL.md files, lookup finds the loaded entry."""
    index = load_fase_index(str(skill_index_path))

    # Round-trip: every skill loaded must be retrievable by its fase ID
    for fase_id, skill in index.items():
        result = load_fase_skill(str(skill_index_path), fase_id)
        assert result is not None
        assert fase_id in result or skill.title in result
```

---

## Common Configuration

### conftest.py (root)

```python
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires real DB/Docker")
    config.addinivalue_line("markers", "agent: requires mocked LLM")
    config.addinivalue_line("markers", "e2e: full scan flow, manual only")
```

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    integration: requires real PostgreSQL or Docker daemon
    agent: agent behavior tests with mocked LLM
    e2e: full scan flow (manual, requires API keys)
```

---

## Layer 1: Unit Test Patterns

### Pydantic model validation

```python
import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from pentest.models.scan_output import ScanReport, Finding

class ScanReportFactory(ModelFactory):
    __model__ = ScanReport

class FindingFactory(ModelFactory):
    __model__ = Finding

def test_finding_id_pattern():
    """Finding ID must match FIND-XXX pattern."""
    finding = FindingFactory.build(id="FIND-001")
    assert finding.id == "FIND-001"

def test_finding_invalid_id_rejected():
    """Invalid finding ID raises ValidationError."""
    with pytest.raises(ValidationError):
        FindingFactory.build(id="INVALID")

def test_scan_report_serialization_roundtrip():
    """ScanReport survives JSON serialization roundtrip."""
    report = ScanReportFactory.build()
    json_str = report.model_dump_json()
    restored = ScanReport.model_validate_json(json_str)
    assert restored == report
```

### Table-driven tests (parametrize)

```python
import pytest

@pytest.mark.parametrize("command,expected_blocked", [
    ("nmap -sV target.com", False),
    ("DROP TABLE users", True),
    ("curl -X DELETE https://target.com/api", True),
    ("nuclei -u target.com", False),
    ("msfconsole -x exploit", True),
    ("rm -rf /", True),
    ("pip install requests", False),
])
def test_command_filter(command, expected_blocked):
    """Destructive commands are blocked, safe commands pass."""
    result = is_command_blocked(command)
    assert result == expected_blocked
```

### Port allocation formula

```python
@pytest.mark.parametrize("flow_id,expected_ports", [
    (1, [28002, 28003]),
    (2, [28004, 28005]),
    (100, [28200, 28201]),
])
def test_port_allocation(flow_id, expected_ports):
    """Port allocation follows deterministic formula."""
    ports = allocate_ports(flow_id)
    assert ports == expected_ports
```

### Recon detector with respx (realistic HTTP fixtures)

Use `respx` to mock HTTP responses with realistic HTML/JS that exercises the actual regex patterns
in the detector code. See `references/real-data-fixtures.md` for ready-made fixtures.

```python
import pytest
import respx
from pentest.recon.supabase import detect_supabase
from pentest.models.recon import SupabaseDetectionResult

# Realistic fixtures — must contain patterns that the detector regex actually matches
HTML_WITH_SCRIPTS = """
<!DOCTYPE html>
<html lang="en">
<head><script src="/assets/app.abc123.js"></script></head>
<body><div id="root"></div></body>
</html>
"""

JS_WITH_SUPABASE = (
    '!function(){"use strict";'
    'const e="https://xyzproject.supabase.co",'
    't="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.fakeSignature1234567890";'
    'supabase.createClient(e,t)}();'
)


@respx.mock
async def test_detect_supabase_high_confidence():
    """Supabase detector finds URL + anon key in JS bundle, verification returns 200."""
    respx.get("https://example.com/").respond(200, text=HTML_WITH_SCRIPTS)
    respx.get("https://example.com/assets/app.abc123.js").respond(200, text=JS_WITH_SUPABASE)
    respx.get("https://xyzproject.supabase.co/rest/v1/").respond(200, text="[]")

    result = await detect_supabase("https://example.com")
    assert isinstance(result, SupabaseDetectionResult)
    assert result.confidence == "high"
    assert result.project_id == "xyzproject"
    assert result.anon_key.startswith("eyJhbGci")
```

### Custom API framework detection with headers/cookies

```python
import respx
from pentest.recon.custom_api import detect_custom_api

@respx.mock
async def test_detect_django_from_cookies():
    """Django detected via csrftoken cookie in response."""
    respx.get("https://target.local/").respond(
        200,
        text="<html><body>Login</body></html>",
        headers={"set-cookie": "csrftoken=abc123; Path=/; SameSite=Lax"},
    )

    result = await detect_custom_api("https://target.local")
    assert result is not None
    assert result.framework == "django"
    assert "cookie:django" in result.scan_path


@respx.mock
async def test_detect_nextjs_from_html():
    """Next.js detected from /_next/ paths and __NEXT_DATA__ script tag."""
    nextjs_html = '''
    <div id="__next"><h1>App</h1></div>
    <script id="__NEXT_DATA__" type="application/json">{"page":"/"}</script>
    <script src="/_next/static/chunks/main.js" defer></script>
    '''
    respx.get("https://target.local/").respond(200, text=nextjs_html)
    # Next.js sites skip GraphQL/Meteor/sockjs probes — only OpenAPI probes happen
    respx.get("https://target.local/openapi.json").respond(404)
    respx.get("https://target.local/swagger.json").respond(404)
    respx.get("https://target.local/docs").respond(404)
    respx.get("https://target.local/api-docs").respond(404)

    result = await detect_custom_api("https://target.local")
    assert result is not None
    assert result.framework == "nextjs"
```

### Tool factory with realistic Docker mock

```python
from unittest.mock import MagicMock
from pentest.tools.terminal import create_terminal_tool

def test_terminal_tool_nmap_output():
    """Terminal tool returns realistic nmap output from Docker exec."""
    mock_docker = MagicMock()
    mock_docker.exec_command.return_value = (
        "Starting Nmap 7.94\\n"
        "PORT    STATE SERVICE VERSION\\n"
        "22/tcp  open  ssh     OpenSSH 8.9p1\\n"
        "80/tcp  open  http    Apache httpd 2.4.52\\n"
    )
    tool = create_terminal_tool(mock_docker, "kali-container-abc")
    result = tool.run({
        "input": "nmap -sV target.local",
        "cwd": "/work",
        "timeout": 120,
        "message": "Port scan",
    })
    assert "22/tcp" in result
    assert "Apache" in result
    mock_docker.exec_command.assert_called_once()
```

---

## Layer 2: Integration Test Patterns

### PostgreSQL with testcontainers

```python
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a real PostgreSQL with pgvector for the test session."""
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        dbname="testdb",
    ) as pg:
        yield pg

@pytest_asyncio.fixture
async def db_session(postgres_container):
    """Create async engine and session, rollback after each test."""
    url = postgres_container.get_connection_url().replace(
        "psycopg2", "asyncpg"
    )
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
    await engine.dispose()
```

### CRUD test

```python
@pytest.mark.integration
async def test_create_flow(db_session):
    """Create a flow and read it back."""
    flow = await create_flow(db_session, CreateFlowParams(
        title="Test scan",
        model="claude-sonnet-4-6",
    ))
    assert flow.id is not None
    assert flow.status == FlowStatus.CREATED

    fetched = await get_flow(db_session, flow.id)
    assert fetched.title == "Test scan"
```

### Foreign key cascade

```python
@pytest.mark.integration
async def test_flow_cascade_deletes_containers(db_session):
    """Deleting a flow cascades to its containers."""
    flow = await create_flow(db_session, ...)
    container = await create_container(db_session, flow_id=flow.id, ...)

    await delete_flow(db_session, flow.id)

    result = await get_container(db_session, container.id)
    assert result is None
```

### Docker container lifecycle

```python
@pytest.mark.integration
async def test_run_and_exec_container(docker_client):
    """Create container, exec command, verify output."""
    container_id = await docker_client.run_container(
        image="python:3.12-slim",
        flow_id=999,
    )
    try:
        output = await docker_client.exec_command(
            container_id, "echo hello"
        )
        assert "hello" in output
    finally:
        await docker_client.remove_container(container_id)
```

### Alembic migration

```python
@pytest.mark.integration
async def test_migration_upgrade_downgrade(postgres_container):
    """Alembic upgrade/downgrade is idempotent."""
    url = postgres_container.get_connection_url()
    # upgrade
    run_alembic(url, "upgrade", "head")
    tables = get_tables(url)
    assert "flows" in tables
    assert "tasks" in tables
    # downgrade
    run_alembic(url, "downgrade", "base")
    tables = get_tables(url)
    assert "flows" not in tables
    # upgrade again (idempotent)
    run_alembic(url, "upgrade", "head")
    tables = get_tables(url)
    assert "flows" in tables
```

---

## Layer 3: Agent Test Patterns

### Mocked LLM with realistic tool call sequences

Use `AIMessage` objects with realistic tool names, arguments (real commands, real paths), and
sequences that match actual agent behavior. See `references/real-data-fixtures.md` for ready-made
LLM response sequences.

```python
import pytest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

@pytest.fixture
def mock_llm():
    """LLM that returns realistic tool call sequence for a Scanner agent."""
    llm = AsyncMock()
    llm.ainvoke.side_effect = [
        # First call: agent runs nmap (realistic command + args)
        AIMessage(content="", tool_calls=[{
            "name": "terminal",
            "args": {
                "input": "nmap -sV -p 1-1000 target.local",
                "cwd": "/work",
                "timeout": 120,
                "message": "Port scan on target",
            },
            "id": "call_001",
        }]),
        # Second call: agent reads scan output file
        AIMessage(content="", tool_calls=[{
            "name": "file",
            "args": {
                "action": "read_file",
                "path": "/work/nmap_output.txt",
                "message": "Read nmap results",
            },
            "id": "call_002",
        }]),
        # Third call: agent submits result via barrier
        AIMessage(content="", tool_calls=[{
            "name": "hack_result",
            "args": {
                "result": "Found 3 open ports: 22/ssh, 80/http (Apache 2.4.52), 5432/postgresql",
                "message": "Port scan complete",
            },
            "id": "call_003",
        }]),
    ]
    return llm
```

### Agent calls correct tools

```python
@pytest.mark.agent
async def test_scanner_uses_terminal_then_hack_result(mock_llm):
    """Scanner agent calls terminal for nmap, reads output, then submits result."""
    agent = ScannerAgent(llm=mock_llm, tools=[terminal, file, hack_result])
    result = await agent.run("Scan target.local for open ports and services")

    calls = [c.tool_calls[0]["name"] for c in mock_llm.ainvoke.call_args_list_responses]
    assert "terminal" in calls
    assert "hack_result" in calls
```

### Reflector corrects missing tool calls

```python
@pytest.mark.agent
async def test_reflector_corrects_text_only_response():
    """Reflector forces agent to use tools when it returns text only."""
    # Agent responds with text, no tool calls
    bad_response = AIMessage(content="I would recommend testing...")
    correction = await reflector.correct(bad_response, context="Test RLS")
    assert "USE the terminal tool" in correction or "must use" in correction.lower()
```

### Reporter produces valid ScanReport

```python
@pytest.mark.agent
async def test_reporter_produces_valid_json(mock_llm_reporter):
    """Reporter output validates against ScanReport Pydantic schema."""
    result = await reporter.run(findings=sample_findings)
    report = ScanReport.model_validate_json(result)
    assert len(report.findings) > 0
    assert all(f.evidence for f in report.findings)
```

### Loop detection

```python
@pytest.mark.agent
async def test_agent_aborts_after_5_same_tool_calls(mock_llm_looping):
    """Agent chain aborts when same tool is called 5+ times."""
    mock_llm_looping.ainvoke.return_value = AIMessage(
        content="", tool_calls=[
            {"name": "terminal", "args": {"command": "curl fail.com"}}
        ]
    )
    with pytest.raises(LoopDetectedError):
        await perform_agent_chain(mock_llm_looping, max_iterations=100)
```

---

## Layer 4: E2E Test Patterns

### Full scan flow

```python
@pytest.mark.e2e
async def test_full_scan_produces_report(real_llm, docker_client, db_session):
    """Complete scan against test target produces valid ScanReport."""
    flow = await create_flow(db_session, CreateFlowParams(
        title="E2E test scan",
        input="scan https://juice-shop.herokuapp.com",
    ))

    report = await run_scan_flow(flow, llm=real_llm, docker=docker_client)

    assert isinstance(report, ScanReport)
    assert report.target.domain == "juice-shop.herokuapp.com"
    assert len(report.findings) > 0
    # Known vulnerabilities in Juice Shop
    finding_types = [f.type for f in report.findings]
    assert any(t in finding_types for t in ["xss_reflected", "sql_injection"])
```
