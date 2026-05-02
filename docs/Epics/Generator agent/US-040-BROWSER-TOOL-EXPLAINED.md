---
tags: [agents]
---

# US-040: Browser Tool — Explicacao Detalhada

Este documento explica o padrão de **Async Web Fetching e Content Processing** usado em `src/pentest/tools/browser.py`. Ao contrario do `terminal` e `file` tools (que usam closures para injectar Docker client), o browser tool e uma ferramenta **stateless** mas com requisitos especiais: operacoes I/O nao-bloqueantes, processamento de HTML complexo, e gestao de tamanho de output para nao sobrecarregar o LLM.

---

## Contexto: Por que Browser Tool?

No ciclo de reconnaissance de um pentest, o agente precisa:

1. Descobrir tecnologias e versoes via HTTP headers e HTML parsing
2. Enumerar URLs e paths para atacar
3. Coletar informacao textual (descripcoes, comentarios de HTML)

A browser tool permite isto **sem** instanciar um navegador real (que seria lento e pesado). Em vez disso, faz requisicoes HTTP simples e processa o HTML resultante.

**Porque async?** Porque o agente pode fazer multiplas requisicoes em paralelo (ex: fetch 5 URLs simultaneamente) sem bloquear o event loop.

---

## Schema: BrowserAction

Ficheiro: `src/pentest/models/tool_args.py`

```python
class BrowserAction(BaseModel):
    """Schema for browser tool calls."""
    url: str = Field(..., description="URL to visit")
    action: Literal["markdown", "html", "links"] = Field("markdown", description="Output format")
    message: str = Field(..., description="Short internal description of the browser operation")
```

### Parametros

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| `url` | `str` | Sim | URL completa com protocolo (http/https) |
| `action` | `Literal["markdown", "html", "links"]` | Nao (default: "markdown") | Que tipo de conteudo extrair |
| `message` | `str` | Sim | Descricao humana para logs/audit |

### Acoes

| Acao | Output | Uso |
|---|---|---|
| **markdown** | Texto limpo em markdown (headings, paragrafos, links) | Ler conteudo legivel (tecnologias, versoes) |
| **html** | HTML bruto (so body tag) | Parsing customizado pelo LLM |
| **links** | Lista de URLs unicas encontradas | Enumerar endpoints/paths |

---

## Arquitectura: Browser Tool

Ficheiro: `src/pentest/tools/browser.py`

### Factory: create_browser_tool()

```python
def create_browser_tool() -> BaseTool:
    """Create an async browser tool for fetching and parsing web content.

    Returns a LangChain StructuredTool. All exceptions are caught and
    returned as strings so the agent loop never raises.
    """

    @tool(args_schema=BrowserAction)
    async def browser(url: str, action: str = "markdown", message: str = "") -> str:
        """Fetch and process web content from a URL.

        Supports three actions:
        - 'markdown': Extract and convert body content to markdown.
        - 'html': Return the raw HTML body (truncated to 16KB).
        - 'links': Extract all unique URLs from <a> tags.

        All output is truncated to 16,000 characters. Errors are returned
        as strings beginning with 'browser tool error:'.
        """
        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.get(url)  # type: ignore[no-any-return]
                response.raise_for_status()
                html = response.text

            if action == "markdown":
                result = _extract_markdown_from_html(html)
            elif action == "html":
                soup = BeautifulSoup(html, "html.parser")  # type: ignore[no-any-return]
                body = soup.find("body")
                result = str(body) if body else html
            elif action == "links":
                result = _extract_links_from_html(html, url)
            else:
                result = f"browser tool error: unknown action '{action}'"

            return _truncate_output(result)
        except asyncio.TimeoutError:
            return f"browser tool error: request timeout after 30 seconds for {url}"
        except Exception as e:
            return f"browser tool error: {e}"

    return browser
```

### Por que Async?

```python
async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
    response = await client.get(url)
```

**Async permite:**

| Caso | Bloqueante (sync) | Nao-bloqueante (async) |
|---|---|---|
| Fetch 1 URL (10ms) | Aguarda 10ms | Aguarda 10ms (mesmo) |
| Fetch 5 URLs em paralelo | Aguarda 5 × 10ms = 50ms | Aguarda 10ms (paralelo!) |
| Multiplos agentes | Cada um bloqueia | Event loop roteiam (time-sharing) |

A tool tool e `async` porque:
1. LangGraph suporta async tools nativamente (via `arun()`)
2. Permite o agente fazer multiplas requisicoes sem serializar
3. Integra-se com contexto asyncio de producao (FastAPI, etc.)

### SSL Verification: verify=False

```python
async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
```

**O que significa `verify=False`:**

```python
# verify=True (default)
# Valida certificado SSL via CA chain
# Rejeita self-signed, expired, etc.
GET https://target.local/  → SSL Error (self-signed cert)

# verify=False (nosso caso)
# Ignora validacao SSL
# Aceita qualquer certificado
GET https://target.local/  → 200 OK (mesmo com self-signed)
```

**Por que para penetration testing?**

| Cenario | Certificado | verify=True | verify=False |
|---|---|---|---|
| Prod (trusted CA) | Valido | OK | OK |
| Intranet corporativa | Self-signed | FAIL | OK ✓ |
| Lab pentesting | Self-signed | FAIL | OK ✓ |
| Dev/staging | Self-signed | FAIL | OK ✓ |

Em pentest, o target frequentemente tem certificados auto-assinados (self-signed) e nao confiamos na CA publica. `verify=False` permite a ferramenta funcionar sem warnings.

**Aviso:** Isto nao deve ser usado em producao para conexoes a servidores de terceiros. Soh no contexto controlado de pentest.

### Timeout: 30 Segundos

```python
async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
```

Se a URL nao responder em 30 segundos, lanca `asyncio.TimeoutError`:

```python
except asyncio.TimeoutError:
    return f"browser tool error: request timeout after 30 seconds for {url}"
```

30 segundos e tempo razoavel para:
- Requisicoes normais: ~100ms
- Requisicoes lentas: ~5s
- Servidores muito lentosou mal-configurados: < 30s
- Requests verdadeiramente travadas: > 30s → timeout

---

## Content Processing: Extract & Transform

### 1. Markdown Extraction

```python
def _extract_markdown_from_html(html: str) -> str:
    """Extract markdown from HTML body, using markdownify if available."""
    try:
        soup = BeautifulSoup(html, "html.parser")  # type: ignore[no-any-return]
        body = soup.find("body")
        if body is None:
            body = soup
        body_html = str(body)

        if HAS_MARKDOWNIFY:
            return md(body_html)

        # Fallback: extract text with some structure preserved
        text_parts = []
        for elem in body.find_all(["h1", "h2", "h3", "p", "li", "a", "code"]):
            if elem.name in ["h1", "h2", "h3"]:
                text_parts.append(f"\n{'#' * int(elem.name[1])} {elem.get_text(strip=True)}\n")
            elif elem.name == "p":
                text_parts.append(elem.get_text(strip=True) + "\n")
            elif elem.name == "li":
                text_parts.append(f"- {elem.get_text(strip=True)}\n")
            elif elem.name == "a":
                href = elem.get("href", "#")
                text = elem.get_text(strip=True)
                text_parts.append(f"[{text}]({href})")
            elif elem.name == "code":
                text_parts.append(f"`{elem.get_text(strip=True)}`")
        return "".join(text_parts)
    except Exception as e:
        return f"Error extracting markdown: {e}"
```

#### Passo 1: Parse HTML com BeautifulSoup

```python
soup = BeautifulSoup(html, "html.parser")
```

BeautifulSoup converte string HTML para arvore de nodes. O `"html.parser"` usa o parser built-in do Python (nao precisa de lxml ou html5lib externos).

#### Passo 2: Encontrar o Body

```python
body = soup.find("body")
if body is None:
    body = soup
```

Extrai soh o conteudo `<body>`. Se nao existir (HTML invalido), fallback para root. Isto reduz ruido (remove `<head>`, `<script>`, `<style>`).

#### Passo 3: Prioridade a Markdownify

```python
if HAS_MARKDOWNIFY:
    return md(body_html)
```

A biblioteca `markdownify` faz conversao HTML → Markdown muito mais robusta. Se estiver instalada, usa-a.

```python
# Exemplo com markdownify
HTML: <h1>Title</h1><p>Para <strong>bold</strong>.</p>
Markdown: # Title\n\nPara **bold**.\n
```

#### Passo 4: Fallback Manual

Se `markdownify` nao estiver disponivel, extrai soh elementos importantes:

```python
for elem in body.find_all(["h1", "h2", "h3", "p", "li", "a", "code"]):
    if elem.name in ["h1", "h2", "h3"]:
        text_parts.append(f"\n{'#' * int(elem.name[1])} {elem.get_text(strip=True)}\n")
    elif elem.name == "p":
        text_parts.append(elem.get_text(strip=True) + "\n")
    # ... etc
```

Mapeia elementos HTML para markdown:

| HTML | Markdown |
|---|---|
| `<h1>`, `<h2>`, `<h3>` | `# `, `## `, `### ` |
| `<p>` | Paragrafos (newline) |
| `<li>` | `- ` (lista) |
| `<a href="...">text</a>` | `[text](url)` |
| `<code>` | `` `code` `` |

**Resultado**: Texto limpo e estruturado, ideial para o LLM ler.

### 2. Links Extraction

```python
def _extract_links_from_html(html: str, base_url: str) -> str:
    """Extract unique absolute URLs from <a> tags."""
    try:
        soup = BeautifulSoup(html, "html.parser")  # type: ignore[no-any-return]
        links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.startswith("http"):
                links.add(href)
            elif href.startswith("/"):
                # Make absolute URL from base domain
                try:
                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)
                    links.add(absolute_url)
                except Exception:
                    pass
        return "\n".join(sorted(links))
    except Exception as e:
        return f"Error extracting links: {e}"
```

#### Extrair URLs Absolutas

Problema: URLs relativas sao inuteis para o agente:

```html
<a href="/admin">Admin</a>          ← Relativa
<a href="https://evil.com">Evil</a> ← Absoluta
```

Solucao: usar `urljoin()` para converter relativas em absolutas:

```python
from urllib.parse import urljoin

base_url = "https://target.com/app/page"

urljoin(base_url, "/admin")           → "https://target.com/admin"
urljoin(base_url, "help")             → "https://target.com/app/help"
urljoin(base_url, "https://evil.com") → "https://evil.com"
```

#### Logica de Dispatch

```python
if href.startswith("http"):
    links.add(href)  # Ja e absoluta
elif href.startswith("/"):
    absolute_url = urljoin(base_url, href)  # Converter para absoluta
    links.add(absolute_url)
```

Ignora:
- Links `#ancoras` (mesma pagina)
- Links `javascript:` (nao URLs)
- Links `mailto:` (nao HTTP)

#### Resultado

```python
return "\n".join(sorted(links))
```

Lista de URLs unicas, uma por linha, ordenadas alfabeticamente:

```
https://target.com/admin
https://target.com/api
https://target.com/dashboard
https://target.com/login
```

---

## Truncation Logic: 16KB Limit

Ficheiro: constante no topo

```python
MAX_OUTPUT_LENGTH = 16000
```

Funcao:

```python
def _truncate_output(text: str) -> str:
    """Truncate text to MAX_OUTPUT_LENGTH and append truncation marker if needed."""
    if len(text) > MAX_OUTPUT_LENGTH:
        return text[:MAX_OUTPUT_LENGTH] + "\n...[truncated]"
    return text
```

### Por que 16KB?

LLMs tem **context window** (limite de tokens que conseguem processar). O Claude 3.5 Sonnet tem ~200K tokens, mas:

1. **Historico de conversa** consome tokens (mensagens anteriores)
2. **System prompt** consome tokens
3. **Tool outputs** consumem tokens
4. **Precisamos deixar espaco** para a proxima resposta do LLM

Cenario real:

```
System prompt:           2,000 tokens
Historico (5 turnos):    5,000 tokens
Tool output (sem limite): 50,000 tokens ← Problema!
LLM resposta:            ~1,000 tokens

Total: 58,000 tokens de um orçamento de 100,000
```

Se nao truncarmos, um HTML grande (ex: Netflix homepage) pode ser 100KB+, consumindo 30K+ tokens. Rapidamente atingimos limite.

### 16KB e Equilibrio

```python
MAX_OUTPUT_LENGTH = 16000  # ~4,000 tokens (aprox)
```

| Limite | Tokens | Util | Problema |
|---|---|---|---|
| Sem limite | 30K+ | Completo | Consome contexto rapidamente |
| 4KB | ~1K | Muito pouco | Perda de informacao |
| **16KB** | ~4K | Bom equilibrio | Suficiente info, sem excesso |
| 64KB | ~16K | Muito | Pode sobrecarregar |

### Exemplo de Truncacao

```python
# Input
html_grande = "<html><body>" + "x" * 30000 + "</body></html>"  # 30KB

# Output
resultado = _truncate_output(html_grande)

# Resultado
len(resultado) == 16000 + len("\n...[truncated]")  # ~16020 chars
resultado[-20:]  # "...\n...[truncated]"
```

O LLM ve `...[truncated]` e entende que foi cortado. Pode pedir mais especificamente (ex: "fetch so a tabela de precos").

---

## Action Dispatch: Trio de Modos

```python
if action == "markdown":
    result = _extract_markdown_from_html(html)
elif action == "html":
    soup = BeautifulSoup(html, "html.parser")  # type: ignore[no-any-return]
    body = soup.find("body")
    result = str(body) if body else html
elif action == "links":
    result = _extract_links_from_html(html, url)
else:
    result = f"browser tool error: unknown action '{action}'"
```

### Markdown Action

```python
if action == "markdown":
    result = _extract_markdown_from_html(html)
```

**Quando:** LLM quer ler informacao textual

**Exemplo:**
```
LLM: "Fetch the homepage e ve que versao de software e usada"
tool: browser(url="https://target.com", action="markdown")
Result:
  # Welcome to Nginx 1.20.1

  Our service runs on Ubuntu 20.04...
```

### HTML Action

```python
elif action == "html":
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    result = str(body) if body else html
```

**Quando:** LLM quer parsing customizado ou analise estrutural

**Exemplo:**
```
LLM: "Preciso de analisar a estrutura da pagina"
tool: browser(url="https://target.com/form", action="html")
Result:
  <body>
    <div class="login-form">
      <input name="username" />
      <input name="password" />
      <button>Login</button>
    </div>
  </body>
```

### Links Action

```python
elif action == "links":
    result = _extract_links_from_html(html, url)
```

**Quando:** LLM quer enumerar endpoints

**Exemplo:**
```
LLM: "Enumera todos os links da homepage"
tool: browser(url="https://target.com", action="links")
Result:
  https://target.com/admin
  https://target.com/api
  https://target.com/dashboard
  https://target.com/login
  https://target.com/products
```

---

## Error Handling: Strings, Nunca Exceptions

```python
try:
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text
    # ... processing ...
    return _truncate_output(result)
except asyncio.TimeoutError:
    return f"browser tool error: request timeout after 30 seconds for {url}"
except Exception as e:
    return f"browser tool error: {e}"
```

### Tipos de Erros Tratados

| Excecao | Causa | Return |
|---|---|---|
| `asyncio.TimeoutError` | URL nao respondeu em 30s | `"browser tool error: request timeout..."` |
| `httpx.ConnectError` | Host nao resolveu / recusou conexao | `"browser tool error: [HTTPError]"` |
| `httpx.HTTPStatusError` | 404, 500, etc (via `raise_for_status()`) | `"browser tool error: [HTTPError]"` |
| `Exception` (generico) | Qualquer outra excecao | `"browser tool error: [details]"` |

### Exemplo: URL Morta

```python
result = browser(url="https://this-domain-does-not-exist.xyz")

# Internamente:
# httpx.get() → ConnectError (name resolution failed)
# except Exception as e → return f"browser tool error: {e}"

# Retorna:
"browser tool error: [Errno -2] Name or service not known"
```

LLM ve o erro e pode:
- Tentar outra URL
- Logar e continuar
- Informar que target nao esta acessivel

**Nunca raise** — o agente loop nunca vê excecoes, soh strings de erro.

---

## Mock Strategy: Testes sem Rede

```python
def create_mock_browser_tool() -> BaseTool:
    """Create a mock browser tool for testing without network access."""

    @tool(args_schema=BrowserAction)
    async def browser(url: str, action: str = "markdown", message: str = "") -> str:
        """Mock browser tool that returns predictable responses for testing."""
        if action == "markdown":
            return f"Mock markdown content from {url}"
        elif action == "html":
            return f"<html><body>Mock HTML from {url}</body></html>"
        elif action == "links":
            return f"https://example.com\nhttps://test.com"
        else:
            return f"browser tool error: unknown action '{action}'"

    return browser
```

### Uso em Testes

```python
# tests/unit/test_generator.py
from pentest.tools.browser import create_mock_browser_tool

def test_generator_with_mock():
    mock_browser = create_mock_browser_tool()

    agent = create_agent_graph(
        llm=mock_llm,
        tools=[mock_browser],  # Nao precisa rede
        barrier_names={"subtask_list"}
    )

    result = agent.invoke({"messages": [...]})
    assert result["barrier_hit"] is True
```

### Vantagens

| Aspecto | Mock | Real |
|---|---|---|
| Requisitos | Python + pytest | Python + httpx + rede |
| Velocidade | Instantaneo (< 1ms) | Lento (100ms-5s) |
| Determinismo | Sempre mesmo resultado | Depende do servidor |
| CI/CD | Funciona offline | Requer rede/VPN |
| Desenvolvimento | Rapido feedback | Mais lento |

---

## Uso End-to-End: Reconnaissance Agent

### Cenario: Descobrir Tecnologias

```python
from pentest.tools.browser import create_browser_tool
from pentest.agents.base import create_agent_graph

# Criar agent
recon_agent = create_agent_graph(
    llm=ChatAnthropic(model="claude-sonnet-4-5"),
    tools=[create_browser_tool()],
    barrier_names={"scan_complete"},
    max_iterations=10,
)

# Invocar
result = recon_agent.invoke({
    "messages": [
        SystemMessage("Tu es o agente de reconnaissance. Descobre tecnologias..."),
        HumanMessage("Target: https://vulnerable-app.local:8443"),
    ]
})
```

### 3 Turnos: Fetch → Parse → Enum

```
[Turno 1]
LLM: "Vou fetch a homepage e ver que tecnologia usa"
tool_calls: [{
    "name": "browser",
    "args": {
        "url": "https://vulnerable-app.local:8443",
        "action": "markdown",
        "message": "Fetch homepage"
    }
}]

Browser:
  - httpx GET https://vulnerable-app.local:8443
  - Response 200, HTML ~5KB
  - Extract markdown (markdownify)
  - Return "Welcome to Django 3.2.5\nRunning on Ubuntu 20.04..."

Result:
  "Welcome to Django 3.2.5\n..."

[Turno 2]
LLM: "Vi que e Django 3.2.5. Vou verificar a versao do Bootstrap"
tool_calls: [{
    "name": "browser",
    "args": {
        "url": "https://vulnerable-app.local:8443",
        "action": "html",
        "message": "Check HTML for Bootstrap version"
    }
}]

Browser:
  - httpx GET (cached, rapido)
  - Extract body tag
  - Return HTML puro

Result:
  "<body><link rel='stylesheet' href='...bootstrap-4.6.1.css'>"

[Turno 3]
LLM: "Via Bootstrap 4.6.1. Agora vou enumerar endpoints"
tool_calls: [{
    "name": "browser",
    "args": {
        "url": "https://vulnerable-app.local:8443",
        "action": "links",
        "message": "Enumerate all endpoints"
    }
}]

Browser:
  - httpx GET
  - Extract all <a href>
  - Resolve relativas para absolutas (urljoin)
  - Return lista ordenada

Result:
  "https://vulnerable-app.local:8443/admin\n
   https://vulnerable-app.local:8443/api\n
   https://vulnerable-app.local:8443/login"

[Turno 4 - Optional]
LLM: "Tenho informacao suficiente. Django 3.2.5, Bootstrap 4.6.1, endpoints: admin, api, login"
tool_calls: [{
    "name": "scan_complete",
    "args": {
        "findings": {
            "framework": "Django 3.2.5",
            "frontend": "Bootstrap 4.6.1",
            "endpoints": ["/admin", "/api", "/login"]
        }
    }
}]

Agent Termina (barrier_hit = True)
```

---

## Testes: Validacao com Respx

Ficheiro: `tests/unit/tools/test_browser.py`

### Mock HTTP com Respx

```python
import respx
import httpx

@pytest.mark.asyncio
async def test_browser_tool_markdown_extraction():
    """Test markdown extraction from HTML content."""
    tool = create_browser_tool()
    html_content = """
    <html><body>
        <h1>Page Title</h1>
        <p>This is a paragraph.</p>
    </body></html>
    """

    with respx.mock:
        # Mock a requisicao
        respx.get("http://example.com").mock(
            return_value=httpx.Response(200, text=html_content)
        )

        # Chamar a tool
        result = await tool.arun({
            "url": "http://example.com",
            "action": "markdown",
            "message": "test"
        })

        # Validar
        assert isinstance(result, str)
        assert "Title" in result or "paragraph" in result
```

### O que Respx Faz

```python
with respx.mock:
    respx.get("http://example.com").mock(...)
```

Intercepta requests HTTP e devolve resposta pre-definida **sem fazer conexao real**:

```python
# Sem respx (real)
GET http://example.com → DNS lookup → TCP connect → HTTP get → (slow)

# Com respx (mock)
GET http://example.com → Lookup em mock → Return resposta def (rapido)
```

### Validacao de Truncacao

```python
@pytest.mark.asyncio
async def test_browser_tool_truncation():
    """Test that output is truncated to 16KB."""
    tool = create_browser_tool()
    large_content = f"<html><body>{'x' * 20000}</body></html>"

    with respx.mock:
        respx.get("http://example.com").mock(
            return_value=httpx.Response(200, text=large_content)
        )
        result = await tool.arun({
            "url": "http://example.com",
            "action": "html",
            "message": "test"
        })

        # Validacoes
        assert len(result) <= 16030  # Max 16KB + marker
        assert "...[truncated]" in result
```

---

## Type Annotations: # type: ignore[no-any-return]

```python
response = await client.get(url)  # type: ignore[no-any-return]
```

O `httpx.AsyncClient` tem tipo generico complexo que Mypy nao consegue inferir automaticamente. O `# type: ignore[no-any-return]` diz a Mypy: "Confia, isto e uma resposta valida de httpx".

```python
soup = BeautifulSoup(html, "html.parser")  # type: ignore[no-any-return]
```

Idem para BeautifulSoup — retorna um tipo complexo que Mypy quer validar.

Alternativa (mais verbose):

```python
from typing import cast

response: httpx.Response = cast(httpx.Response, await client.get(url))
```

Mas `# type: ignore` e mais limpo para bibliotecas dinamicas.

---

## Resumo: Arquitetura do Browser Tool

| Componente | Proposito | Detalhe |
|---|---|---|
| **httpx.AsyncClient** | HTTP fetching nao-bloqueante | verify=False, timeout=30s |
| **BeautifulSoup** | HTML parsing e extraccion | Fallback se markdownify nao disponivel |
| **markdownify** | HTML → Markdown | Optional, melhora qualidade |
| **urljoin** | URL relativa → absoluta | Enumeration de endpoints |
| **Truncation (16KB)** | Gestao de contexto LLM | Evita sobrecarregar |
| **Error handling** | Strings em vez de exceptions | Nunca bloqueia agent loop |
| **Async** | Multiplas requisicoes paralelas | Melhor performance |

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-037-BASE-GRAPH-EXPLAINED]] — StateGraph, BarrierAwareToolNode
- [[US-038-BARRIERS-EXPLAINED]] — Barrier tools e terminacao
- [[US-039-TERMINAL-FILE-EXPLAINED]] — Factory pattern, closures
- [[AGENT-ARCHITECTURE]] — Contexto de delegação e papel do Browser no ecossistema
- **src/pentest/tools/browser.py** — Code completo
- **src/pentest/models/tool_args.py** — BrowserAction schema
- **tests/unit/tools/test_browser.py** — Testes com respx e pytest.mark.asyncio
