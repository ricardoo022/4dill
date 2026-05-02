---
tags: [agents]
---

# US-056: DuckDuckGo search tool — Explicacao Detalhada

Este documento explica a implementacao da US-056 em `src/pentest/tools/duckduckgo.py`, `tests/unit/tools/test_duckduckgo.py` e `pyproject.toml`.

---

## Contexto

A US-056 introduz o primeiro motor de pesquisa web real para o Searcher, sem dependencias de API key.

1. O Searcher ja tinha contratos de dados (`SearchAction`, US-054), mas ainda usava stubs para pesquisa externa.
2. Esta US cria uma tool LangChain concreta com `@tool(args_schema=SearchAction)`.
3. A implementacao privilegia robustez operacional: erros como string, output truncado, e default de timeout.
4. A pesquisa usa `duckduckgo-search` (PyPI), evitando scraping HTML manual.
5. O modulo adiciona `is_available()` para detectar indisponibilidade de runtime/rede sem quebrar o loop do agente.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `pyproject.toml` | Adiciona dependencia runtime `duckduckgo-search` |
| `src/pentest/tools/duckduckgo.py` | Implementa a tool `duckduckgo`, formatacao, truncacao e `is_available()` |
| `tests/unit/tools/test_duckduckgo.py` | Valida comportamento funcional, schema, erros, truncacao e disponibilidade |

---

## Referencia PentAGI (Go)

### `search` (`pentagi/backend/pkg/tools/duckduckgo.go`, linhas 166-230)

```go
client.Timeout = duckduckgoTimeout

for attempt := 0; attempt < duckduckgoMaxRetries; attempt++ {
	req, err := http.NewRequestWithContext(ctx, "POST", duckduckgoSearchURL, strings.NewReader(formData))
	if err != nil {
		return "", fmt.Errorf("failed to create search request: %w", err)
	}

	req.Header.Set("User-Agent", duckduckgoUserAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")

	resp, err := client.Do(req)
	if err != nil {
		if attempt == duckduckgoMaxRetries-1 {
			return "", fmt.Errorf("failed to execute search after %d attempts: %w", duckduckgoMaxRetries, err)
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(time.Second):
		}
		continue
	}
}
```

### `IsAvailable` (`pentagi/backend/pkg/tools/duckduckgo.go`, linhas 527-531)

```go
func (d *duckduckgo) IsAvailable() bool {
	return d.enabled()
}
```

**Diferenca chave:** no Go, o motor DuckDuckGo e baseado em HTTP + parsing HTML + retries; nesta US Python, foi adotado o pacote `duckduckgo-search` para reduzir fragilidade e simplificar manutencao.

---

## `pyproject.toml` (`pyproject.toml`)

```toml
dependencies = [
    "docker>=7.0",
    "duckduckgo-search>=6.0",
    "langchain>=0.3",
]
```

| Linha(s) | Explicacao |
|---|---|
| `+ "duckduckgo-search>=6.0"` | Introduz dependencia runtime para disponibilizar `DDGS` no modulo da tool. |

---

## `duckduckgo.py` (`src/pentest/tools/duckduckgo.py`)

### Imports, constantes e carregamento condicional do cliente

```python
import importlib
from typing import Any

from langchain_core.tools import tool

from pentest.models.search import SearchAction

try:
    DDGS: Any = importlib.import_module("duckduckgo_search").DDGS
except ImportError:  # pragma: no cover - exercised via is_available and runtime path
    DDGS = None

MAX_OUTPUT_LENGTH = 16000
DEFAULT_REGION = "wt-wt"
DEFAULT_TIMEOUT_SECONDS = 30
```

| Linha(s) | Explicacao |
|---|---|
| 5-15 | Resolve import opcional de `DDGS` sem falha no import do modulo quando o package nao existir. |
| 18-20 | Define os limites/valores padrao exigidos pela US: truncacao 16KB, regiao `wt-wt`, timeout 30s. |

**Porque e assim?** O modulo precisa continuar carregavel mesmo sem dependencia instalada, para que o runtime do agente devolva erro legivel em vez de excecao de import.

### `_truncate_output` e `_format_results`

```python
def _truncate_output(text: str) -> str:
    if len(text) > MAX_OUTPUT_LENGTH:
        return text[:MAX_OUTPUT_LENGTH] + "\n...[truncated]"
    return text

def _format_results(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title = str(item.get("title") or "Untitled result")
        url = str(item.get("href") or "URL not available")
        snippet = str(item.get("body") or "").strip()
        lines.append(f"{index}. [{title}] - {url}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()
```

| Funcao | Entrada | Saida | Regra |
|---|---|---|---|
| `_truncate_output` | `text: str` | `str` | Corta para 16KB e adiciona `...[truncated]` |
| `_format_results` | `results: list[dict[str, Any]]` | `str` | Converte resultados DDGS para lista numerada legivel |

### `is_available()`

```python
def is_available() -> bool:
    if DDGS is None:
        return False

    try:
        with DDGS(timeout=5) as ddgs:
            probe = ddgs.text(
                "test",
                region=DEFAULT_REGION,
                safesearch="moderate",
                max_results=1,
            )
            next(iter(probe or []), None)
        return True
    except Exception:
        return False
```

| Passo | Comportamento |
|---|---|
| 1 | Falha rapida (`False`) se `DDGS` nao estiver disponivel no runtime. |
| 2 | Executa um probe curto (`timeout=5`) para validar acessibilidade basica. |
| 3 | Nunca propaga excecoes; retorna apenas `True/False`. |

### `duckduckgo` tool (publica)

```python
@tool(args_schema=SearchAction)
def duckduckgo(query: str, max_results: int = 5, message: str = "") -> str:
    del message

    if DDGS is None:
        return "duckduckgo search error: duckduckgo-search package not installed"

    try:
        with DDGS(timeout=DEFAULT_TIMEOUT_SECONDS) as ddgs:
            raw_results = ddgs.text(
                query,
                region=DEFAULT_REGION,
                safesearch="moderate",
                max_results=max_results,
            )
            results = list(raw_results or [])
    except Exception as exc:
        return f"duckduckgo search error: {exc}"

    if not results:
        return f"No results found for: {query}"

    return _truncate_output(_format_results(results))
```

| Parametro | Tipo | Default/Constraint | Explicacao |
|---|---|---|---|
| `query` | `str` | obrigatorio (via `SearchAction`) | Query de pesquisa. |
| `max_results` | `int` | `5` (limites 1..10 via `SearchAction`) | Quantidade de resultados enviados ao motor. |
| `message` | `str` | obrigatorio no schema | Campo de contexto para o agente; nao interfere na query. |

Fluxo de controlo:

```
┌─ chamada duckduckgo(query, max_results, message)
│
├─ DDGS indisponivel? ── Sim ──> "duckduckgo search error: ...package not installed"
│                     └─ Nao
│
├─ Executa DDGS.text(...)
│   ├─ Excecao? ── Sim ──> "duckduckgo search error: {exc}"
│   └─ Nao
│
├─ Lista vazia? ── Sim ──> "No results found for: {query}"
│              └─ Nao
│
└─ Formata + trunca output ──> texto final para o LLM
```

---

## `test_duckduckgo.py` (`tests/unit/tools/test_duckduckgo.py`)

### Helper de mocking

```python
def _setup_ddgs(monkeypatch, text_return=None, text_side_effect=None):
    ddgs_instance = MagicMock()
    if text_side_effect is not None:
        ddgs_instance.text.side_effect = text_side_effect
    else:
        ddgs_instance.text.return_value = text_return
    ddgs_class = MagicMock()
    ddgs_class.return_value.__enter__.return_value = ddgs_instance
    ddgs_class.return_value.__exit__.return_value = False
    monkeypatch.setattr(duckduckgo_module, "DDGS", ddgs_class)
    return ddgs_class, ddgs_instance
```

| Linha(s) | Explicacao |
|---|---|
| 10-21 | Injeta `DDGS` mockado no modulo testado e controla retorno/erro de `text()`. |

### Cobertura por requisito da US-056

| Requisito | Teste |
|---|---|
| Output formatado | `test_duckduckgo_formats_search_results` |
| 0 resultados | `test_duckduckgo_no_results` |
| Erro em string | `test_duckduckgo_returns_error_string_on_engine_exception` |
| Pass-through de `max_results` | `test_duckduckgo_max_results_passthrough` |
| JSON schema de function calling | `test_duckduckgo_tool_schema_is_function_calling_compatible` |
| Truncacao 16KB | `test_duckduckgo_output_truncates_at_16kb` |
| `is_available()` true/false | `test_is_available_returns_true_when_engine_reachable`, `test_is_available_returns_false_on_engine_error` |

---

## Exemplo Completo

```python
from pentest.tools.duckduckgo import duckduckgo

result = duckduckgo.invoke(
    {
        "query": "CVE-2023-38408 OpenSSH advisory",
        "max_results": 3,
        "message": "Find authoritative vulnerability sources",
    }
)
```

Saida esperada (shape):

```text
1. [Title] - URL
   Snippet...

2. [Title] - URL
   Snippet...
```

---

## Padrao de Implementacao

Padrao reutilizavel para search tools neste projeto:

1. Declarar `@tool(args_schema=...)` para garantir schema Pydantic.
2. Encapsular dependencia externa com fallback seguro no import.
3. Nunca propagar excecoes para o loop do agente; retornar erro textual padronizado.
4. Limitar tamanho de output para controlar contexto do LLM.
5. Cobrir comportamento via mocks de cliente externo em testes unitarios.

---

## Questoes Frequentes

### P: Porque `message` e descartada com `del message`?

A: O schema exige o campo para manter consistencia de tool-calling e rastreabilidade, mas o motor DuckDuckGo nao precisa dele para executar a pesquisa.

### P: Porque `is_available()` faz probe real e nao apenas check de import?

A: A US pede validacao de acessibilidade; apenas importar o pacote nao detecta bloqueios de rede/firewall.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-054-SEARCH-MODELS-EXPLAINED]] — contrato `SearchAction` usado pela tool.
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]] — etapa terminal do Searcher no graph.
- **`src/pentest/tools/duckduckgo.py`** — implementacao da US-056.
