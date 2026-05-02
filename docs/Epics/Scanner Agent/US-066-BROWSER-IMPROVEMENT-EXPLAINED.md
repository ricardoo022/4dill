---
tags: [scanner-agent, browser-tool, playwright]
---

# US-066: Melhoria da Tool de Browser para Workflows do Scanner — Explicação Detalhada

Esta US transformou a tool `browser` de um simples fetcher HTTP num browser headless de alta fidelidade (Playwright), capaz de observar aplicações modernas (SPAs) e capturar screenshots.

Ficheiros alterados/criados:
- **`src/pentest/models/tool_args.py`**: Upgrade do schema `BrowserAction`
- **`src/pentest/tools/browser.py`**: Implementação do modo `advanced` com Playwright
- **`src/pentest/templates/prompts/scanner_system.md.j2`**: Instruções para o agente sobre o uso do browser
- **`src/pentest/templates/prompts/scanner_user.md.j2`**: Template de subtask para o Scanner
- **`tests/unit/tools/test_browser.py`**: Testes de schema e modo `light`
- **`tests/integration/tools/test_browser.py`**: Testes de renderização JS e screenshots

---

## Contexto

O Scanner Agent precisa de observar targets reais que, frequentemente, usam frameworks modernos (React, Vue, Angular). Um fetch HTTP simples (usado na US-040) não executa JavaScript, resultando em páginas "vazias" ou mensagens de "Loading...". Esta melhoria introduz o Playwright para garantir que o agente vê o mesmo que um utilizador real, permitindo identificar vulnerabilidades em SPAs.

---

## Upgrade do Schema: `BrowserAction`

O modelo `BrowserAction` em **`src/pentest/models/tool_args.py`** foi expandido para suportar o novo modo de operação.

### Tabela de Campos: `BrowserAction`

| Campo | Tipo | Default | Descrição |
|---|---|---|---|
| `url` | `str` | (Obrigatório) | URL a visitar. |
| `mode` | `Literal["light", "advanced"]` | `"light"` | Modo de operação. `light` é rápido (HTTP); `advanced` é completo (JS). |
| `action` | `Literal["markdown", "html", "links", "screenshot"]` | `"markdown"` | O que extrair ou fazer na página. |
| `message` | `str` | (Obrigatório) | Justificação da operação para o log/utilizador. |

---

## Implementação: `src/pentest/tools/browser.py`

A tool agora utiliza uma abordagem híbrida:
1. **Modo `light`**: Utiliza `httpx` para máxima velocidade quando JS não é necessário.
2. **Modo `advanced`**: Utiliza `playwright` (Chromium headless) para renderização completa.

### Fluxo de Execução (Modo Advanced)

1. **Lançamento**: Abre uma instância do Chromium via `async_playwright()`.
2. **Navegação**: Acede ao URL e aguarda o evento `networkidle` (até 60s) para garantir que o JS terminou de carregar.
3. **Ação**:
    - Se `action='screenshot'`, captura o ecrã e guarda em `/tmp/screenshots/`.
    - Caso contrário, extrai o HTML renderizado via `page.content()`.
4. **Parsing**: Converte o HTML (seja ele bruto ou renderizado) para Markdown ou extrai links usando os parsers existentes.
5. **Cleanup**: Garante que o browser é fechado corretamente mesmo em caso de erro.

### Screenshots

As screenshots são guardadas com um timestamp no nome para evitar colisões. O caminho é retornado ao agente como uma string informativa.

```python
if action == "screenshot":
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"screenshot_{int(asyncio.get_event_loop().time())}.png"
    filepath = SCREENSHOT_DIR / filename
    await page.screenshot(path=str(filepath))
    return f"Screenshot saved to: {filepath}"
```

---

## Prompts do Scanner

Foram criados os templates Jinja2 iniciais para o Scanner Agent, integrando o conhecimento sobre como usar as novas capacidades do browser.

### `scanner_system.md.j2`

Define as diretrizes de uso:
- Usar `light` para documentação e sites estáticos.
- Usar `advanced` para SPAs ou quando o conteúdo parecer incompleto.
- Usar `screenshot` para validação visual.

---

## Como Testar

### 1. Testes Unitários (Schema e HTTP)
Provam que o modo default continua a ser o leve e rápido.
```bash
pytest tests/unit/tools/test_browser.py -v
```

### 2. Testes de Integração (Playwright)
Provam a renderização de JavaScript e a geração de ficheiros de imagem.
```bash
pytest tests/integration/tools/test_browser.py -v
```

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Scanner Agent/US-061-SCANNER-AGENT-HUB|Scanner Agent Hub]]
