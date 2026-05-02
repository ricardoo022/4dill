---
tags: [agents]
---

# US-057: Tavily search tool — Explicacao Detalhada

Este documento explica a implementacao da US-057 em `src/pentest/tools/tavily.py`, `tests/unit/tools/test_tavily.py` e `pyproject.toml`.

---

## Contexto

A US-057 introduz o segundo motor de pesquisa web real para o Searcher, com suporte a API key opcional.

1. O Searcher ja tinha o DuckDuckGo (US-056), um motor gratis mas com resultados basicos.
2. Tavily e um motor de pesquisa otimizado especificamente para LLMs — retorna resultados mais ricos (conteudo completo, scores de relevancia, respostas directas).
3. Diferenca critica: Tavily e condicional. So esta disponivel quando `TAVILY_API_KEY` esta configurado (env var). Sem a key, o Searcher cai para DuckDuckGo.
4. A implementacao usa `tavily-python` (PyPI), um SDK gerenciado que lida com autenticacao, retries e parsing.
5. O modulo adiciona `is_available()` para permitir ao Searcher detectar se Tavily pode ser usado, sem quebrar o pipeline.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `pyproject.toml` | Adiciona dependencia runtime `tavily-python>=0.7.20` |
| `src/pentest/tools/tavily.py` | Implementa a tool `tavily_search`, formatacao, truncacao e `is_available()` |
| `tests/unit/tools/test_tavily.py` | Valida comportamento funcional, schema, erros, truncacao e disponibilidade (21 testes) |

---

## Referencia PentAGI (Go)

### `tavily.go` (`pentagi/backend/pkg/tools/tavily.go`, linhas 1-150)

```go
func (t *tavily) Search(ctx context.Context, query string, args json.RawMessage) (string, error) {
	var params SearchRequest
	if err := json.Unmarshal(args, &params); err != nil {
		return "", fmt.Errorf("invalid search parameters: %w", err)
	}

	client := &http.Client{
		Timeout: 30 * time.Second,
	}

	payload := map[string]interface{}{
		"api_key":         t.apiKey,
		"query":           query,
		"max_results":     params.MaxResults,
		"search_depth":    "basic",
		"include_answer":  true,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", tavilyURL, bytes.NewReader(body))
	// ... HTTP request execution ...

	return formatResults(results, answer), nil
}
```

**Diferenca chave:** O PentAGI usa HTTP directo com client manual. Esta US Python adota o package `tavily-python` para:
- Abstrair detalhes de auth (API key injection automática)
- Simplificar parsing da resposta JSON
- Reduzir codigo boilerplate (HTTP headers, timeouts, etc.)

---

## `pyproject.toml`

```toml
dependencies = [
    "docker>=7.0",
    "duckduckgo-search>=6.0",
    "tavily-python>=0.7.20",
    "langchain>=0.3",
    "langchain-anthropic>=0.3",
]
```

| Linha(s) | Explicacao |
|---|---|
| `+ "tavily-python>=0.7.20"` | Adiciona SDK Tavily como dependencia runtime. Verso minima 0.7.20 garante suporte a `include_answer` e `search_depth`. |

---

## `tavily_search` (`src/pentest/tools/tavily.py`)

### Constantes e carregamento condicional do cliente

```python
import importlib
from typing import Any

try:
    TavilyClient: Any = importlib.import_module("tavily").Client
except ImportError:  # pragma: no cover
    TavilyClient = None

MAX_OUTPUT_LENGTH = 16000
CONTENT_CHUNK_LENGTH = 2048
```

| Elemento | Explicacao |
|---|---|
| `importlib.import_module("tavily")` | Carregamento dinamico do package. Se nao instalado, continua sem crash. |
| `TavilyClient = None` | Fallback safe: qualquer tentativa de usar `None.search()` vai retornar erro legivel, nao traceback. |
| `MAX_OUTPUT_LENGTH = 16000` | Limite global de output formatado. Se ultrapassado, trunca com "...[truncated]". |
| `CONTENT_CHUNK_LENGTH = 2048` | Limite por resultado (2KB). Protege contra contexto inflado. |

---

### Funcao `_truncate_content()`

```python
def _truncate_content(text: str, max_len: int = CONTENT_CHUNK_LENGTH) -> str:
    """Truncate text to the configured content length."""
    if len(text) > max_len:
        return text[:max_len] + "...[truncated]"
    return text
```

| Linha(s) | Explicacao |
|---|---|
| `if len(text) > max_len:` | Se conteudo excede limite, corta na marca e adiciona indicador. |
| `text[:max_len] + "...[truncated]"` | Responde com `...[truncated]` como aviso, nao silencioso. |

---

### Funcao `_format_results()`

```python
def _format_results(
    results: list[dict[str, Any]],
    answer: str | None = None,
) -> str:
    """Format Tavily search results to a readable output."""
    lines: list[str] = []

    # Add answer section if available
    if answer:
        lines.append(f"Answer: {answer}")
        lines.append("")
        lines.append("Sources:")
    else:
        lines.append("Sources:")

    # Add sources with scores
    for index, item in enumerate(results, start=1):
        title = str(item.get("title") or "Untitled result")
        url = str(item.get("url") or "URL not available")
        score = item.get("score", 0.0)
        content = str(item.get("content") or "").strip()

        # Format with score
        lines.append(f"{index}. [{title}] (score: {score:.2f}) - {url}")

        # Add truncated content if available
        if content:
            truncated_content = _truncate_content(content)
            lines.append(f"   {truncated_content}")

        lines.append("")

    return "\n".join(lines).rstrip()
```

| Bloco | Explicacao |
|---|---|
| `if answer:` | Se Tavily retornou resposta directa (sintetizada pela IA), aparece primeiro na secao "Answer:". |
| `for index, item in enumerate(results, start=1):` | Iterar cada resultado com indice (1-indexed para leitura humana). |
| `str(item.get(...) or "...")` | Defensive: se campo esta ausente/None, retorna valor default. Tavily responde com estrutura consistente, mas este guard protege. |
| `score: {score:.2f}` | Formata score a 2 casas decimais (ex: `0.95`, nao `0.954321`). |
| `_truncate_content(content)` | Aplica limite de 2KB ao conteudo de cada resultado. |

**Exemplo de output:**
```
Answer: OpenSSH versions prior to 7.4 are vulnerable to remote code execution through PAM authentication bypass.

Sources:
1. [CVE-2023-1234 OpenSSH RCE] (score: 0.95) - https://nvd.nist.gov/vuln/detail/CVE-2023-1234
   A vulnerability in OpenSSH 7.4 and earlier allows remote attackers to execute arbitrary code...

2. [Exploit PoC OpenSSH CVE-2023-1234] (score: 0.87) - https://exploit-db.com/exploits/12345
   This PoC demonstrates the vulnerability chain. First, attacker sends crafted PAM message...
```

---

### Funcao `is_available()`

```python
def is_available() -> bool:
    """Check if Tavily API key is configured in environment."""
    if TavilyClient is None:
        return False

    api_key = os.getenv("TAVILY_API_KEY")
    return bool(api_key and api_key.strip())
```

| Linha(s) | Explicacao |
|---|---|
| `if TavilyClient is None:` | Se `tavily-python` nao esta instalado, nao tenta carregar API key. |
| `os.getenv("TAVILY_API_KEY")` | Busca env var. Se nao existe, retorna `None`. |
| `bool(api_key and api_key.strip())` | Verifica se existe E nao e so whitespace (e.g., `" "` e considerado nao disponivel). |

**Uso no Searcher:** O agente chama `is_available()` durante inicializacao. Se False, Tavily nao e incluida na lista de tools disponiveis. O agente cai para DuckDuckGo.

---

### Tool `tavily_search`

```python
@tool(args_schema=SearchAction)
def tavily_search(query: str, max_results: int = 5, message: str = "") -> str:
    """Search the web with Tavily and return readable text results.

    Uses AI-powered search with answer generation and source ranking.
    Respects max_results limit (1-10) and returns formatted results with scores.
    """
    del message  # Suppress unused parameter warning

    if TavilyClient is None:
        return "tavily search error: tavily-python package not installed"

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or not api_key.strip():
        return "tavily search error: TAVILY_API_KEY environment variable not configured"

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=True,
        )
    except Exception as exc:
        return f"tavily search error: {exc}"

    # Extract results and answer
    results = response.get("results", [])
    answer = response.get("answer")

    if not results:
        return f"No results found for: {query}"

    formatted = _format_results(results, answer)
    # Truncate overall output to configured max
    if len(formatted) > MAX_OUTPUT_LENGTH:
        formatted = formatted[:MAX_OUTPUT_LENGTH] + "\n...[truncated]"

    return formatted
```

#### Parametros

| Parametro | Tipo | Default | Descricao |
|---|---|---|---|
| `query` | `str` | — | Pesquisa solicitada. Obrigatorio. Exemplo: `"CVE-2023-1234 OpenSSH"` |
| `max_results` | `int` | `5` | Numero de resultados a retornar (1-10, imposto pelo schema `SearchAction`). |
| `message` | `str` | `""` | Contexto/descricao da pesquisa (fornecida pelo Searcher agent). Usado para logging, nao afeta API. |

#### Fluxo de execucao

1. **Decorador `@tool(args_schema=SearchAction)`**: LangChain vincula esta funcao como tool com validacao de schema. O LLM pode chamar via function calling.

2. **Verificacoes iniciais:**
   - Se `TavilyClient` é `None` → retorna error string (package nao instalado)
   - Se `TAVILY_API_KEY` nao configurada → retorna error string

3. **API call:**
   - Instancia `TavilyClient(api_key=...)`
   - Chama `client.search(...)` com parametros fixos:
     - `search_depth="basic"` — nao usa deep research (mais rapido, suficiente para pentest)
     - `include_answer=True` — pede sintese de resposta (LLM + sources)
   - Se qualquer exception → retorna error string (nunca raise)

4. **Processamento:**
   - Extrai `results` (lista de sources) e `answer` (sintese) da resposta
   - Se 0 resultados → retorna mensagem "No results found"
   - Formata com `_format_results(...)`

5. **Truncacao:**
   - Se output > 16KB → corta e adiciona "...[truncated]"

#### Por que sempre retorna string, nunca raise?

O agente LLM (LangGraph) precisa processar resposta da tool como continuacao de pensamento. Se a tool lanca exception, o LLM nao consegue raciocinar sobre o erro. Retornando string descritiva:
- O agente ve erro e pode **tentar novamente** ou **pivotear para outra tool**
- O loop nao quebra
- O contexto da conversa permanece valido

---

## Exemplo Completo

### Cenario: Agent Searcher procura info sobre CVE

```
Entrada do LLM:
{
  "query": "CVE-2024-1086 privilege escalation Linux",
  "max_results": 3,
  "message": "Find technical details about Linux kernel vuln for pentest targeting Ubuntu 22.04"
}

Passos internos:
1. is_available() verificada durante setup → True (TAVILY_API_KEY existe)
2. tavily_search() e adicionada a agent tools
3. LLM chama tavily_search com parametros acima
4. TavilyClient(api_key=...).search(...) retorna:
   {
     "results": [
       {
         "title": "CVE-2024-1086: Netfilter use-after-free",
         "url": "https://nvd.nist.gov/vuln/detail/CVE-2024-1086",
         "content": "A vulnerability in the Linux kernel netfilter module...",
         "score": 0.96
       },
       ...
     ],
     "answer": "CVE-2024-1086 is a privilege escalation flaw in Linux..."
   }
5. _format_results(...) transforma em:
   Answer: CVE-2024-1086 is a privilege escalation flaw in Linux...

   Sources:
   1. [CVE-2024-1086: Netfilter use-after-free] (score: 0.96) - https://nvd.nist.gov/vuln/detail/CVE-2024-1086
      A vulnerability in the Linux kernel netfilter module...

   ... (mais resultados)

Saida:
Retorna string formatada acima. Agent vê resposta, integra no seu contexto,
e continua reasoning (p.ex., "Sources mostram que apenas Ubuntu 22.04.3+ pode be affected").
```

---

## Padrão de Implementação

A US-057 estabelece o padrão para **search tools com API key condicional**:

1. **Package externo via importlib**: importar em try/except, nao em topo. Permite graceful fallback.
2. **`is_available()` funcao**: sempre presente, sempre verifica ambas:
   - Package disponivel (importlib successful)
   - Env var configurada (e.g., `TAVILY_API_KEY`)
3. **Erros como string**: nunca raise. Formato: `"<tool> error: <mensagem>"` ou `"No results found for: <query>"`
4. **Parametros via `args_schema=SearchAction`**: validacao automática pelo LangChain. O schema define min/max values.
5. **Truncacao em dois niveis**:
   - Nível conteudo: cada result truncado a 2KB
   - Nível global: output total truncado a 16KB

Este padrão reutiliza-se em futuras tools (p.ex., search via APIs commerciais, proprietary search engines).

---

## Como `is_available()` Funciona na Inicializacao do Agent

O `is_available()` nao e apenas uma funcao — e o **mecanismo central que permite ao agent adaptar-se aos recursos disponiveis sem quebrar o pipeline**.

### Problema Resolvido

Sem `is_available()`, o agente entraria em loop infinito:

```
Cenario: Sem TAVILY_API_KEY configurada

1. Agent inicia com tools = [tavily_search, duckduckgo, graphiti_search]
2. LLM recebe schema: "Voce pode chamar: tavily_search, duckduckgo, graphiti_search"
3. LLM pensa: "Tavily e melhor para research, vou usar!"
4. LLM chama: tavily_search("CVE-2024-1234")
5. Tool retorna: "tavily search error: TAVILY_API_KEY not configured"
6. LLM: "Hmm, erro... talvez transient? Vou retentar Tavily"
7. Tool retorna: MESMO ERRO
   ... loops 20x ...
8. Adviser intervem: "Voce esta looping, reset"
   ├─ Tempo perdido: ~60 segundos
   ├─ Tokens LLM desperdidos: 20x thinking cycles
   └─ Experiencia do utilizador: muito lenta, confusa
```

Com `is_available()`, o pipeline e **limpo**:

```
Cenario: Com is_available() check

1. Agent inicia — checks:
   ├─ tavily.is_available() → False (no TAVILY_API_KEY)
   ├─ duckduckgo.is_available() → True
   └─ graphiti_search.is_available() → True

2. Tools list criada dinamicamente: [duckduckgo, graphiti_search]

3. LLM recebe schema: "Voce pode chamar: duckduckgo, graphiti_search"
   (Tavily nao aparece!)

4. LLM pensa: "Disponivel: duckduckgo, graphiti_search. Vou usar DuckDuckGo"

5. LLM chama: duckduckgo("CVE-2024-1234")

6. Tool retorna: resultados correctos

7. Agent continua normalmente
   ├─ Tempo: ~3 segundos
   ├─ Tokens LLM: 1x thinking cycle
   └─ Experiencia do utilizador: rapida, respondiva
```

### Fluxo de Inicializacao do Agent

```
┌──────────────────────────────────────────────────────────────────┐
│ FASE 1: Verificar disponibilidade de CADA tool                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│ def create_searcher_agent(llm, db_session):                      │
│     tools_available = []                                         │
│                                                                   │
│     # Check cada tool via is_available()                         │
│     if tavily.is_available():                                    │
│         tools_available.append(tavily.tavily_search)             │
│         print("✓ Tavily (API key configured)")                   │
│     else:                                                         │
│         print("✗ Tavily (skipped)")                              │
│                                                                   │
│     if duckduckgo.is_available():                                │
│         tools_available.append(duckduckgo.duckduckgo)            │
│         print("✓ DuckDuckGo")                                    │
│     else:                                                         │
│         print("✗ DuckDuckGo (skipped)")                          │
│                                                                   │
│     if graphiti_search.is_available():                           │
│         tools_available.append(                                  │
│             graphiti_search.create_tool(db_session)              │
│         )                                                         │
│         print("✓ Graphiti")                                      │
│     else:                                                         │
│         print("✗ Graphiti (skipped)")                            │
│                                                                   │
│     # Resultado: tools_available = [duckduckgo, graphiti_search] │
│     #            (Tavily excluido!)                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ FASE 2: Criar agent com APENAS tools disponiveis                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│ agent = create_agent_graph(                                      │
│     llm=llm,                                                     │
│     tools=tools_available,  ← FILTRADO!                          │
│     barrier_names={"search_result"},                             │
│     max_iterations=100                                           │
│ )                                                                 │
│                                                                   │
│ # Dentro de create_agent_graph:                                  │
│ llm_with_tools = llm.bind_tools(tools)  ← Bind APENAS available  │
│                                                                   │
│ # LLM system prompt recebe schema de 2 tools:                    │
│ # [duckduckgo, graphiti_search]                                  │
│ # (tavily_search nao aparece!)                                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ FASE 3: Agent executa com tools disponiveis apenas              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│ Iteracao 1:                                                      │
│   LLM: "Pesquisar CVE-2024-1234"                                 │
│   LLM: "Tools disponiveis: duckduckgo, graphiti_search"          │
│   LLM chama: duckduckgo("CVE-2024-1234")                         │
│       → Retorna resultados OK                                    │
│                                                                   │
│ Iteracao 2:                                                      │
│   LLM: "Tenho resultados, processando..."                        │
│   LLM chama: search_result(findings="...")  ← Barrier tool       │
│       → Agent completa normalmente                               │
│                                                                   │
│ Resultado: PIPELINE LIMPO, sem loops                             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Dois Cenarios: O que o LLM Ve

#### Cenario A: SEM Tavily API key

```
┌────────────────────────────────────────────────────┐
│ Comando de inicializacao:                          │
├────────────────────────────────────────────────────┤
│ $ export TAVILY_API_KEY=              # (vazio)    │
│ $ python create_searcher.py                        │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Checks:                                            │
├────────────────────────────────────────────────────┤
│ tavily.is_available():                             │
│   ├─ TavilyClient package: ✓ instalado            │
│   ├─ TAVILY_API_KEY env var: ✗ nao set            │
│   └─ Result: False                                 │
│                                                    │
│ duckduckgo.is_available():                         │
│   ├─ DDGS package: ✓ instalado                    │
│   ├─ Probe duckduckgo.com: ✓ alcancavel           │
│   └─ Result: True                                  │
│                                                    │
│ graphiti_search.is_available():                    │
│   ├─ GraphitiClient: ✓ alcancavel                 │
│   └─ Result: True                                  │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Tools list final:                                  │
├────────────────────────────────────────────────────┤
│ [duckduckgo, graphiti_search]                      │
│ (tavily_search EXCLUIDO)                           │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ LLM System Prompt (schema das tools):              │
├────────────────────────────────────────────────────┤
│ "You are a Searcher agent. Available tools:        │
│                                                    │
│  1. duckduckgo(query, max_results, message)        │
│  2. graphiti_search(questions, type, message)      │
│  3. search_result(findings, message)               │
│                                                    │
│  (tavily_search is NOT available)"                 │
└────────────────────────────────────────────────────┘

Resultado: LLM nunca vai tentar chamar Tavily!
```

#### Cenario B: COM Tavily API key

```
┌────────────────────────────────────────────────────┐
│ Comando de inicializacao:                          │
├────────────────────────────────────────────────────┤
│ $ export TAVILY_API_KEY="tvly-abc123xyz"           │
│ $ python create_searcher.py                        │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Checks:                                            │
├────────────────────────────────────────────────────┤
│ tavily.is_available():                             │
│   ├─ TavilyClient package: ✓ instalado            │
│   ├─ TAVILY_API_KEY env var: ✓ set                │
│   └─ Result: True  ← DIFERENCA!                   │
│                                                    │
│ duckduckgo.is_available():                         │
│   ├─ DDGS package: ✓ instalado                    │
│   ├─ Probe duckduckgo.com: ✓ alcancavel           │
│   └─ Result: True                                  │
│                                                    │
│ graphiti_search.is_available():                    │
│   ├─ GraphitiClient: ✓ alcancavel                 │
│   └─ Result: True                                  │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Tools list final:                                  │
├────────────────────────────────────────────────────┤
│ [tavily_search, duckduckgo, graphiti_search]       │
│ (TODAS tools disponiveis!)                         │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ LLM System Prompt (schema das tools):              │
├────────────────────────────────────────────────────┤
│ "You are a Searcher agent. Available tools:        │
│                                                    │
│  1. tavily_search(query, max_results, message)     │
│  2. duckduckgo(query, max_results, message)        │
│  3. graphiti_search(questions, type, message)      │
│  4. search_result(findings, message)               │
│                                                    │
│  (tavily_search is available!)"                    │
└────────────────────────────────────────────────────┘

Resultado: LLM pode escolher entre 3 search tools!
```

### A "Porta de Entrada" — Duas Gates

```
┌──────────────────────────────────────────────────────────┐
│ def is_available() -> bool:                              │
├──────────────────────────────────────────────────────────┤
│                                                           │
│ # GATE 1: Package instalado?                             │
│ if TavilyClient is None:                                 │
│     return False  ← FALHA: package nao instalado         │
│                                                           │
│ # GATE 2: API key configurado?                           │
│ api_key = os.getenv("TAVILY_API_KEY")                    │
│ return bool(api_key and api_key.strip())                │
│                                                           │
│ # Possibilidades:                                        │
│ • api_key = None → False (nao set)                       │
│ • api_key = "" → False (empty string)                    │
│ • api_key = "   " → False (apenas whitespace)           │
│ • api_key = "tvly-xyz" → True ✓ (ready to use!)         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Comparacao com DuckDuckGo

DuckDuckGo nao precisa de API key, mas ainda faz `is_available()` porque pode estar **inacessivel**:

```python
def is_available() -> bool:
    """Check if DuckDuckGo service is reachable."""
    if DDGS is None:
        return False  # Package check

    try:
        # Active probe: test API connectivity
        with DDGS(timeout=5) as ddgs:
            probe = ddgs.text("test", max_results=1)
            next(iter(probe or []), None)
        return True  # Service works!
    except Exception:
        return False  # Network down, geo-blocked, or service down
```

**Por que Tavily e diferente:**
- Tavily: so precisa de credenciais (API key). Se a key e valida, o serviço responde.
- DuckDuckGo: precisa de rede + servico accessible (sem auth). Pode falhar por network/geo-blocking.

### Summary: O Padrao `is_available()`

| Etapa | O que acontece | Resultado |
|-------|--|--|
| **Startup** | Cada tool chama seu `is_available()` | True/False para cada tool |
| **Filtering** | Agent coleciona apenas True tools | `tools_available = [...]` |
| **Binding** | LLM recebe schema de tools disponiveis | LLM so "conhece" tools validas |
| **Execution** | LLM chama apenas tools que existem | Sem loops, sem erros esperados |

**Resultado final:** O agent adapta-se dinamicamente aos recursos disponiveis. Se Tavily nao esta configurado, o agent nunca tenta usá-lo. Se esta, o agent o prefere (melhor qualidade).

---

## Questoes Frequentes

### P: Por que nao usar `langchain-community.tools.TavilySearchResults`?

A: O wrapper LangChain (em `langchain-community`) oferece conveniencia mas **nao deixa controlar o schema de args**. O Searcher precisa que todas as tools usem `args_schema=SearchAction` para consistencia com LLM. Usar o SDK directo (`tavily-python`) da-nos controlo total.

### P: O que acontece se `TAVILY_API_KEY` expira ou fica invalida?

A: O API call falhara com `ValueError` ou similar. A funcao retorna `"tavily search error: Invalid API key"` (ou mensagem similar do SDK). O agent vê este erro e pode **retentar com DuckDuckGo** ou **reportar para o operador**.

### P: Por que `search_depth="basic"` e nao `"advanced"`?

A: "advanced" demora mais tempo (seconds) e custa mais tokens. Para pentest em tempo-real, "basic" oferece trade-off bom: resultados relevantes sem overhead. Se futuro demandar profundidade extra, pode parametrizar isto.

### P: Porque e que o `message` parameter existe se nao e usado?

A: Contrato com `SearchAction` (US-054). O `message` permite ao agent descrever contexto da pesquisa (p.ex., `"Looking for nginx bypass techniques"`). Internamente, nao afeta a API call Tavily, mas aparece em logs e permite audit trail da decision do agent.

### P: Como garantir que content truncado a 2KB nao perde informacao critica?

A: Tavily ordena resultados por score. Os primeiros resultados (scores altos) contem synthesized answer. Se conteudo de alta relevancia e truncado, a sintese ja capturou o essencial.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-054-SEARCH-MODELS-EXPLAINED]] — defines `SearchAction` schema used aqui
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]] — defines `search_result` barrier tool
- [[US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED]] — first search engine (fallback)
- [[AGENT-ARCHITECTURE]] — Contexto do Searcher dentro da arquitetura multi-agent
- **src/pentest/tools/tavily.py** — implementacao
- **tests/unit/tools/test_tavily.py** — test suite (21 testes, cobertura 100%)
