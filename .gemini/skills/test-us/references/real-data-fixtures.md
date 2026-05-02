# Real Data Fixtures

Realistic test fixtures for each module. Use these as building blocks when generating tests.
**Never use trivial mocks** like `MagicMock().return_value = "ok"` when a realistic fixture exists.

---

## Recon: HTTP Response Fixtures

All recon detectors use `httpx.AsyncClient` internally. Mock them with `respx` and realistic HTML/JS/headers.

### Supabase HTML + JS Bundle

```python
# Realistic HTML page with script tags (as seen in SPAs using Supabase)
SUPABASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>My App</title>
  <script src="/assets/vendor.abc123.js"></script>
  <script src="/assets/app.def456.js"></script>
</head>
<body><div id="root"></div></body>
</html>
"""

# JS bundle containing Supabase URL and anon key (realistic minified-ish pattern)
SUPABASE_JS_BUNDLE = """
!function(){"use strict";const e="https://xyzproject.supabase.co",t="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5enByb2plY3QiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTcwMDAwMDAwMCwiZXhwIjoxODAwMDAwMDAwfQ.fakeSignatureHere1234567890abcdef";const o=supabase.createClient(e,t)}();
"""

# JS bundle with NO Supabase patterns (control fixture)
CLEAN_JS_BUNDLE = """
!function(){"use strict";console.log("app loaded");const e=document.getElementById("root");e&&(e.innerHTML="<h1>Hello</h1>")}();
"""
```

### Firebase HTML + Config Object

```python
# HTML with inline Firebase config (common in Firebase Hosting deploys)
FIREBASE_INLINE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Firebase App</title>
  <script src="https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js"></script>
  <script>
    var firebaseConfig = {
      apiKey: "AIzaSyD-FAKE-KEY-FOR-TESTING-1234567",
      authDomain: "myproject-12345.firebaseapp.com",
      projectId: "myproject-12345",
      storageBucket: "myproject-12345.appspot.com",
      messagingSenderId: "123456789012",
      appId: "1:123456789012:web:abcdef1234567890"
    };
    firebase.initializeApp(firebaseConfig);
  </script>
</head>
<body><div id="app"></div></body>
</html>
"""

# JS bundle with firebase.initializeApp() call (common in bundled apps)
FIREBASE_JS_BUNDLE = """
!function(){var e={apiKey:"AIzaSyB-ANOTHER-FAKE-KEY-9876543",authDomain:"testapp.firebaseapp.com",projectId:"testapp-prod",storageBucket:"testapp-prod.appspot.com",messagingSenderId:"987654321098",appId:"1:987654321098:web:fedcba0987654321"};firebase.initializeApp(e);window.__FIREBASE__=!0}();
"""

# Firebase URL patterns without full config (medium confidence)
FIREBASE_PARTIAL_JS = """
fetch("https://firestore.googleapis.com/v1/projects/partial-app/databases/(default)/documents/users");
const ws = new WebSocket("wss://partial-app-default-rtdb.firebaseio.com/.ws");
"""
```

### Custom API: Framework Detection Headers + HTML

```python
# Express.js response headers
EXPRESS_HEADERS = {
    "x-powered-by": "Express",
    "content-type": "text/html; charset=utf-8",
    "etag": 'W/"abc123"',
}

# Django response with telltale cookies
DJANGO_HEADERS = {
    "content-type": "text/html; charset=utf-8",
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
}
DJANGO_COOKIES = "csrftoken=abc123def456; Path=/; SameSite=Lax"

# Laravel response cookies
LARAVEL_COOKIES = "laravel_session=eyJpdiI6IjEyMzQ1Njc4OTAiLCJ2YWx1ZSI6ImFiY2RlZiJ9; Path=/; HttpOnly"

# Next.js HTML (contains /_next/ and __NEXT_DATA__)
NEXTJS_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body>
<div id="__next"><div>My Next.js App</div></div>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}},"page":"/","query":{}}</script>
<script src="/_next/static/chunks/main-abc123.js" defer></script>
</body>
</html>
"""

# FastAPI OpenAPI JSON response
FASTAPI_OPENAPI_JSON = """
{
  "openapi": "3.1.0",
  "info": {"title": "My API", "version": "0.1.0"},
  "paths": {
    "/api/v1/users": {"get": {"summary": "List users"}},
    "/api/v1/scans": {"post": {"summary": "Create scan"}}
  }
}
"""

# GraphQL introspection response
GRAPHQL_TYPENAME_RESPONSE = '{"data": {"__typename": "Query"}}'

# WordPress HTML
WORDPRESS_HTML = """
<!DOCTYPE html>
<html lang="en-US">
<head>
<link rel="stylesheet" href="/wp-content/themes/theme/style.css" type="text/css"/>
<script src="/wp-includes/js/jquery/jquery.min.js"></script>
</head>
<body class="home page">
<div id="page"><p>WordPress Site</p></div>
</body>
</html>
"""

# SvelteKit HTML
SVELTEKIT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<link rel="modulepreload" href="/_app/immutable/entry/start.abc123.js">
</head>
<body data-sveltekit-preload-data="hover">
<div style="display:contents">
  <div id="svelte-announcer" aria-live="assertive" aria-atomic="true" class="visually-hidden"></div>
</div>
<script type="module" src="/__sveltekit/env.js"></script>
</body>
</html>
"""

# Meteor HTML + sockjs probe response
METEOR_HTML = """
<!DOCTYPE html><html><head></head><body>
<script type="text/javascript">__meteor_runtime_config__ = METEOR@3.0;</script>
</body></html>
"""
METEOR_SOCKJS_RESPONSE = '{"websocket": true, "cookie_needed": false, "origins": ["*:*"]}'
```

### Subdomains: TLS/DNS/HTTP Fixtures

```python
# Mock subdomain probe responses (status, headers, IP)
SUBDOMAIN_RESPONSES = {
    "https://api.example.com": {"status": 200, "server": "nginx/1.25", "x-powered-by": "Express"},
    "https://admin.example.com": {"status": 302, "location": "https://admin.example.com/login"},
    "https://app.example.com": {"status": 200, "server": "cloudflare"},
    "https://staging.example.com": {"status": 403, "server": "Apache/2.4"},
}

# HTML with subdomain links (for link-based discovery)
MAIN_PAGE_WITH_LINKS = """
<html><body>
<a href="https://api.example.com/v1/docs">API Docs</a>
<a href="https://dashboard.example.com">Dashboard</a>
<a href="mailto:support@example.com">Contact</a>
</body></html>
"""
```

---

## Agent: Realistic LLM Response Sequences

### Generator Plan Response

```python
from langchain_core.messages import AIMessage

# Generator returns a subtask list via barrier tool (realistic plan)
GENERATOR_PLAN_RESPONSE = AIMessage(
    content="",
    tool_calls=[{
        "name": "subtask_list",
        "args": {
            "subtasks": [
                {"title": "Port scan", "description": "Run nmap -sV against target to discover open ports and services", "fase": "fase-1"},
                {"title": "Web fingerprint", "description": "Identify web server, framework, and CMS from headers and HTML patterns", "fase": "fase-1"},
                {"title": "Auth endpoint discovery", "description": "Probe /login, /auth, /api/auth for authentication mechanisms", "fase": "fase-7"},
                {"title": "SQL injection test", "description": "Test input fields with sqlmap for SQL injection vulnerabilities", "fase": "fase-10"},
                {"title": "XSS probe", "description": "Test reflected and stored XSS on user-facing input fields", "fase": "fase-10"},
            ],
            "message": "Generated 5 subtasks targeting open ports, web fingerprinting, auth, SQLi, and XSS"
        },
        "id": "call_gen_001",
    }],
)
```

### Scanner Tool Call Sequence

```python
# Scanner: runs nmap, then reads output, then submits result
SCANNER_NMAP_SEQUENCE = [
    AIMessage(content="", tool_calls=[{
        "name": "terminal",
        "args": {"input": "nmap -sV -p 1-1000 target.local", "cwd": "/work", "timeout": 120, "message": "Port scan on target"},
        "id": "call_scan_001",
    }]),
    AIMessage(content="", tool_calls=[{
        "name": "file",
        "args": {"action": "read_file", "path": "/work/nmap_output.txt", "message": "Read nmap results"},
        "id": "call_scan_002",
    }]),
    AIMessage(content="", tool_calls=[{
        "name": "hack_result",
        "args": {"result": "Port 80 (HTTP), 443 (HTTPS), 5432 (PostgreSQL) open. Apache/2.4.52 on 80/443.", "message": "Port scan complete"},
        "id": "call_scan_003",
    }]),
]
```

### Reflector Correction Scenario

```python
# Agent returns text-only (no tool calls) — Reflector should correct this
BAD_AGENT_RESPONSE = AIMessage(
    content="I would recommend running nmap to discover open ports. You should also check for common web vulnerabilities like SQL injection and XSS.",
    tool_calls=[],
)

# After correction, agent should use tools
CORRECTED_RESPONSE = AIMessage(
    content="",
    tool_calls=[{
        "name": "terminal",
        "args": {"input": "nmap -sV target.local", "cwd": "/work", "timeout": 120, "message": "Running port scan"},
        "id": "call_corrected_001",
    }],
)
```

---

## Models: Realistic Pydantic Instances

### SubtaskList (Generator output)

```python
from pentest.models.subtask import SubtaskInfo, SubtaskList

REALISTIC_SUBTASK_LIST = SubtaskList(
    subtasks=[
        SubtaskInfo(title="Port discovery", description="Scan TCP ports 1-65535 with nmap", fase="fase-1"),
        SubtaskInfo(title="Service fingerprinting", description="Identify service versions on open ports", fase="fase-1"),
        SubtaskInfo(title="Web crawl", description="Crawl web application to map endpoints and forms", fase="fase-3"),
        SubtaskInfo(title="Authentication test", description="Test login endpoints for default credentials and brute-force", fase="fase-7"),
        SubtaskInfo(title="SQL injection", description="Test all input parameters for SQL injection using sqlmap", fase="fase-10"),
    ],
    message="5 subtasks covering discovery through exploitation",
)
```

### BackendProfile (Orchestrator output)

```python
from pentest.models.recon import BackendProfile, SubdomainInfo

SUPABASE_PROFILE = BackendProfile(
    primary_target="https://myapp.vercel.app",
    backend_type="supabase",
    confidence="high",
    scan_path=["fase-1", "fase-3", "fase-5", "fase-7", "fase-10", "fase-16", "fase-20", "fase-21"],
    configs={"project_id": "xyzproject", "anon_key": "eyJhbGci..."},
    subdomains=[
        SubdomainInfo(url="https://api.myapp.vercel.app", status=200, server="Vercel"),
    ],
)

DJANGO_PROFILE = BackendProfile(
    primary_target="https://vulnerable-django.local",
    backend_type="custom_api",
    confidence="medium",
    scan_path=["fase-1", "fase-7", "fase-10", "fase-16", "fase-21"],
    configs={"framework": "django", "auth_mechanism": "cookie"},
    subdomains=[],
)
```

---

## Tools: Docker Client Mock with Realistic Responses

### Terminal Tool with Realistic Command Outputs

```python
from unittest.mock import MagicMock

def create_realistic_docker_mock():
    """Docker client mock that returns realistic command outputs."""
    mock = MagicMock()

    # Map commands to realistic outputs
    command_outputs = {
        "nmap -sV target.local": (
            "Starting Nmap 7.94 ( https://nmap.org )\n"
            "Nmap scan report for target.local (10.0.0.5)\n"
            "PORT    STATE SERVICE VERSION\n"
            "22/tcp  open  ssh     OpenSSH 8.9p1\n"
            "80/tcp  open  http    Apache httpd 2.4.52\n"
            "443/tcp open  ssl     Apache httpd 2.4.52\n"
            "5432/tcp open  postgresql PostgreSQL 16.1\n"
        ),
        "whoami": "root\n",
        "curl -s -o /dev/null -w '%{http_code}' http://target.local": "200",
        "sqlmap -u 'http://target.local/api?id=1' --batch --level=1": (
            "[INFO] testing connection to the target URL\n"
            "[INFO] testing 'AND boolean-based blind'\n"
            "[CRITICAL] all tested parameters do not appear to be injectable\n"
        ),
    }

    def exec_side_effect(container_id, command, cwd="/work", timeout=60, detach=False):
        for pattern, output in command_outputs.items():
            if pattern in command:
                return output
        return f"$ {command}\n(no output)\n"

    mock.exec_command.side_effect = exec_side_effect
    return mock
```

### File Tool with Realistic File Contents

```python
def create_realistic_file_mock():
    """Docker client mock for file operations with realistic contents."""
    mock = MagicMock()

    file_contents = {
        "/work/nmap_output.txt": (
            "# Nmap 7.94 scan initiated\n"
            "Host: 10.0.0.5 (target.local)\tStatus: Up\n"
            "22/tcp\topen\tssh\tOpenSSH 8.9p1\n"
            "80/tcp\topen\thttp\tApache httpd 2.4.52\n"
        ),
        "/etc/os-release": 'ID=kali\nVERSION_ID="2024.1"\n',
        "/work/exploit.py": "#!/usr/bin/env python3\nimport requests\n# exploit code\n",
    }

    def read_side_effect(container_id, path):
        if path in file_contents:
            return file_contents[path]
        raise FileNotFoundError(f"No such file: {path}")

    def write_side_effect(container_id, path, content):
        file_contents[path] = content
        return f"wrote {len(content)} bytes to {path}"

    mock.read_file.side_effect = read_side_effect
    mock.write_file.side_effect = write_side_effect
    return mock
```
