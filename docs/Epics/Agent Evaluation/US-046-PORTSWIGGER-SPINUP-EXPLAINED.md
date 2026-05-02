---
tags: [evaluation]
---

# US-046: PortSwigger Spinup Automation — Explicacao Detalhada

Este documento explica, em detalhe, a implementacao da `US-046` em `tests/evals/spinup.py`, `tests/evals/test_spinup.py`, e `tests/evals/test_spinup_e2e.py`, incluindo dois bugs de login descobertos durante a implementacao e a integracao com o pipeline de CI.

---

## Contexto

A `US-046` formaliza a automacao de spinup de labs PortSwigger para o eval runner. Antes desta US, `spinup.py` era um script simples sem tratamento de erros, com um selector CSS desatualizado e um bug silencioso na verificacao de sessao. Esta US adiciona:

- Excecoes tipadas com mensagens acionaveis para falhas de autenticacao e timeout
- Persistencia de sessao correta (evita login repetido entre spinups)
- Modo batch para spinar subsets completos (`--batch-subset quick`)
- Testes unitarios com Playwright mockado (sem browser real, correm em CI)
- Testes e2e contra o site real PortSwigger (requerem credenciais, `workflow_dispatch` only)

O `spinup.py` é infraestrutura de avaliacao, nao codigo de producao. Vive em `tests/evals/` e nao tem equivalente no PentAGI Go.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `tests/evals/spinup.py` | CLI + funcoes de spinup (modificado) |
| `tests/evals/__init__.py` | Torna `tests/evals` um package Python (novo, vazio) |
| `tests/evals/test_spinup.py` | 10 testes unitarios com Playwright mockado (novo) |
| `tests/evals/test_spinup_e2e.py` | 4 testes e2e contra o site real (novo) |
| `.github/workflows/ci.yml` | Passo de eval unit tests + job `portswigger-spinup` (modificado) |

---

## 1) `tests/evals/spinup.py` — Excecoes e Credenciais

### Novas constantes e excecoes (linhas 25-46)

```python
LABS_FILE = Path(__file__).parent / "datasets" / "portswigger_mvp.json"


class PortSwiggerAuthError(Exception):
    """Raised when credentials are missing or login fails."""


class PortSwiggerTimeoutError(Exception):
    """Raised when a lab fails to spin up within the expected time."""


def _load_credentials() -> tuple[str, str]:
    email = os.environ.get("PORTSWIGGER_EMAIL")
    password = os.environ.get("PORTSWIGGER_PASSWORD")
    if not email or not password:
        raise PortSwiggerAuthError(
            "Missing credentials: set PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD environment variables."
        )
    return email, password
```

| Simbolo | Tipo | Propósito |
|---|---|---|
| `LABS_FILE` | `Path` | Caminho para `portswigger_mvp.json` — fonte dos URLs por `lab_id` para o modo batch |
| `PortSwiggerAuthError` | `Exception` | Credenciais ausentes ou login falhou — distingue da excecao generica para handling preciso |
| `PortSwiggerTimeoutError` | `Exception` | Timeout no selector do botao ou no URL da instancia — distingue de erros de auth |
| `_load_credentials()` | `→ tuple[str, str]` | Centraliza leitura de env vars; falha imediatamente com mensagem que nomeia ambas as vars |

**Porque `os.environ.get` em vez de `os.environ[...]`?** A versao anterior usava `os.environ["PORTSWIGGER_EMAIL"]` que lanca `KeyError` — uma excecao generica sem contexto. Com `.get()` + verificacao explicita, a mensagem diz exatamente o que fazer: `"set PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD environment variables."` Isto satisfaz a aceita "Erros de auth/timeouts retornam mensagens claras para troubleshooting".

---

## 2) `_login()` — Deteção de falha de autenticacao

```python
async def _login(page: Page, email: str, password: str) -> None:
    await page.goto(f"{PORTSWIGGER_BASE}/users")
    await page.wait_for_selector("#EmailAddress")
    await page.fill("#EmailAddress", email)
    await page.fill("#Password", password)
    await page.click("#Login")
    try:
        await page.wait_for_url(f"{PORTSWIGGER_BASE}/users/youraccount**", timeout=15_000)
    except Exception:
        raise PortSwiggerAuthError(
            "Login failed: check PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD. "
            "The account page was not reached after submitting credentials."
        )
```

A funcao original nao capturava o timeout de `wait_for_url`. Se as credenciais fossem erradas, o Playwright lancava `TimeoutError` (nome generico da biblioteca). A versao nova converte esse erro em `PortSwiggerAuthError` com mensagem explicita: o runner nao precisa de interpretar tracebacks do Playwright.

---

## 3) `_is_logged_in()` — Dois Bugs Corrigidos

```python
async def _is_logged_in(page: Page) -> bool:
    await page.goto(f"{PORTSWIGGER_BASE}/users/youraccount")
    # Logged-in: stays under /users/youraccount (e.g. /users/youraccount/licenses).
    # Not logged-in: redirects to /users?returnurl=... which does NOT start with /users/youraccount.
    return page.url.startswith(f"{PORTSWIGGER_BASE}/users/youraccount")
```

Esta funcao acumulou **dois bugs** que foram descobertos durante os testes e2e reais.

### Bug 1 — Falso positivo com `"youraccount" in page.url`

A versao original usava:

```python
return "youraccount" in page.url
```

**Problema:** Quando nao autenticado, o PortSwigger redireciona para:

```
https://portswigger.net/users?returnurl=%2fusers%2fyouraccount
```

O substring `"youraccount"` aparece **no parametro `returnurl` encoded** da URL de redirect. Resultado: `_is_logged_in` retornava `True` mesmo sem sessao valida — o login era ignorado e o spinup falhava silenciosamente no passo seguinte.

### Bug 2 — Falso negativo com `== f"{PORTSWIGGER_BASE}/users/youraccount"`

A primeira tentativa de correcao usava comparacao exacta:

```python
return page.url.rstrip("/") == f"{PORTSWIGGER_BASE}/users/youraccount"
```

**Problema:** Com sessao valida, o PortSwigger redireciona internamente para:

```
https://portswigger.net/users/youraccount/licenses
```

A URL final tem um sufixo (`/licenses`), entao a comparacao exacta retornava `False` — login era repetido desnecessariamente, reescrevendo o SESSION_FILE.

### Correcao final — `startswith`

```
URL com sessao valida:
  https://portswigger.net/users/youraccount/licenses  → startswith("/users/youraccount") = True ✓

URL sem sessao:
  https://portswigger.net/users?returnurl=%2fusers%2fyouraccount → startswith("/users/youraccount") = False ✓
```

`startswith(f"{PORTSWIGGER_BASE}/users/youraccount")` resolve ambos os casos porque:
- O redirect de login muda o path para `/users?...` (ja nao comeca com `/users/youraccount`)
- O redirect interno de sessao valida acrescenta um sufixo mas mantem o prefixo

---

## 4) `spinup_lab()` — Selector Actualizado e Tratamento de Erros

```python
async def spinup_lab(lab_url: str, *, headless: bool = True) -> str:
    email, password = _load_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        if SESSION_FILE.exists():
            saved = json.loads(SESSION_FILE.read_text())
            await context.add_cookies(saved)

        page = await context.new_page()

        if not await _is_logged_in(page):
            await _login(page, email, password)
            await _save_session(context)

        await page.goto(lab_url)

        # "Access the lab" button — class="button-orange" inside .container-buttons-left
        LAB_BUTTON = ".container-buttons-left a.button-orange"
        try:
            await page.wait_for_selector(LAB_BUTTON, timeout=20_000)
        except Exception:
            raise PortSwiggerTimeoutError(
                f"Timed out waiting for lab launch button on {lab_url}. "
                "The lab page may not have loaded or the selector may have changed."
            )

        async with context.expect_page() as new_page_info:
            await page.click(LAB_BUTTON)

        lab_page = await new_page_info.value
        await lab_page.wait_for_load_state("domcontentloaded")

        try:
            await lab_page.wait_for_url(
                f"**{LAB_INSTANCE_DOMAIN}**",
                timeout=30_000,
            )
        except Exception:
            raise PortSwiggerTimeoutError(
                f"Lab instance URL never resolved for {lab_url}. "
                f"Current URL: {lab_page.url}"
            )

        instance_url = lab_page.url
        await browser.close()
        return instance_url
```

### Fluxo de execucao

```
spinup_lab(lab_url)
  │
  ├─ _load_credentials()
  │     └─ KeyError? → PortSwiggerAuthError (imediato, sem browser)
  │
  ├─ async_playwright() → browser → context
  │
  ├─ SESSION_FILE.exists()?
  │     ├─ Sim → context.add_cookies(saved)
  │     └─ Nao → sem cookies
  │
  ├─ _is_logged_in(page)
  │     ├─ True  → skip login
  │     └─ False → _login() → _save_session() → SESSION_FILE actualizado
  │
  ├─ page.goto(lab_url)
  │
  ├─ wait_for_selector(".container-buttons-left a.button-orange", 20s)
  │     └─ Timeout → PortSwiggerTimeoutError
  │
  ├─ context.expect_page() → click botao → nova aba abre
  │
  ├─ lab_page.wait_for_url("**web-security-academy.net**", 30s)
  │     └─ Timeout → PortSwiggerTimeoutError (inclui URL actual para debug)
  │
  └─ return lab_page.url  (ex: "https://abc123.web-security-academy.net")
```

### Selector CSS actualizado

| Versao | Selector | Motivo da mudanca |
|---|---|---|
| Original | `[widget-id='academy-launchlab'] a` | Web Component custom; removido pelo PortSwigger |
| US-046 | `.container-buttons-left a.button-orange` | Elemento `<a class="button-orange">` dentro de `.container-buttons-left`; detectado por inspecao do DOM com Playwright headless |

O HTML actual do botao e:

```html
<div class="container-buttons-left">
    <a class="button-orange"
       href="/academy/labs/launch/{hash}?referrer=..."
       target="_blank">
        ACCESS THE LAB
    </a>
</div>
```

O atributo `target="_blank"` faz o botao abrir numa nova aba — por isso e usado `context.expect_page()` para capturar essa nova aba antes de clicar.

### `headless=False` — Modo Debug

O parametro `headless` passa directamente para `p.chromium.launch(headless=headless)`. Com `headless=False`, o browser abre uma janela visivel — util para diagnosticar falhas de selector ou comportamentos inesperados do site. Activado via CLI com `--headed`.

---

## 5) `spinup_batch()` — Spinup em Lote

```python
async def spinup_batch(lab_ids: list[str], *, headless: bool = True) -> dict[str, str]:
    with open(LABS_FILE) as f:
        dataset = json.load(f)

    labs_by_id = {lab["lab_id"]: lab for lab in dataset["labs"]}
    results: dict[str, str] = {}

    for lab_id in lab_ids:
        if lab_id not in labs_by_id:
            print(f"[WARN] Unknown lab_id: {lab_id}", file=sys.stderr)
            continue
        lab_url = labs_by_id[lab_id]["lab_url"]
        print(f"[spinup] {lab_id} ...", file=sys.stderr)
        try:
            instance_url = await spinup_lab(lab_url, headless=headless)
            results[lab_id] = instance_url
            print(f"[spinup] {lab_id} -> {instance_url}", file=sys.stderr)
        except (PortSwiggerAuthError, PortSwiggerTimeoutError) as e:
            print(f"[ERROR] {lab_id}: {e}", file=sys.stderr)
            results[lab_id] = ""

    return results
```

| Aspecto | Detalhe |
|---|---|
| Entrada | `lab_ids: list[str]` — IDs do `portswigger_mvp.json` (ex: `["sqli-login-bypass", "xss-reflected-html-nothing-encoded"]`) |
| Saida | `dict[str, str]` — `{lab_id: instance_url}` (string vazia se spinup falhou) |
| Resolucao de URL | Carrega `portswigger_mvp.json`, constroi `{lab_id: lab}` lookup, extrai `lab_url` por ID |
| Tolerancia a falhas | Erros por lab sao capturados e registados em stderr; o batch continua para os restantes |
| IDs desconhecidos | Aviso em stderr e `continue` — nao lanca excecao, nao interrompe o batch |
| Execucao | Sequencial (um lab de cada vez) — evita race conditions de sessao e sobrecarga de browser |

**Porque sequencial e nao paralelo?** Cada `spinup_lab` cria um browser separado. A sessao PortSwigger e partilhada via SESSION_FILE. Execucao paralela criaria race conditions na leitura/escrita do ficheiro de sessao e potencialmente esgotaria recursos (multiplos browsers Chromium simultaneos).

---

## 6) `main()` — CLI Actualizado

```python
async def main() -> None:
    headless = "--headed" not in sys.argv

    if "--batch-subset" in sys.argv:
        idx = sys.argv.index("--batch-subset")
        if idx + 1 >= len(sys.argv):
            print("Usage: python evals/spinup.py --batch-subset <subset_name>", file=sys.stderr)
            sys.exit(1)
        subset_name = sys.argv[idx + 1]
        with open(LABS_FILE) as f:
            dataset = json.load(f)
        if subset_name not in dataset["subsets"]:
            print(f"Error: unknown subset '{subset_name}'", file=sys.stderr)
            sys.exit(1)
        lab_ids = dataset["subsets"][subset_name]["labs"]
        try:
            results = await spinup_batch(lab_ids, headless=headless)
        except PortSwiggerAuthError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(results, indent=2))
        return

    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not positional:
        print("Usage: python evals/spinup.py <portswigger_lab_url>")
        print("       python evals/spinup.py --batch-subset <subset_name> [--headed]")
        sys.exit(1)
    ...
```

### Modos de invocacao

```bash
# Modo 1: Lab individual
python tests/evals/spinup.py https://portswigger.net/web-security/sql-injection/lab-login-bypass

# Modo 2: Lab individual com browser visivel (debug)
python tests/evals/spinup.py <url> --headed

# Modo 3: Batch por subset
python tests/evals/spinup.py --batch-subset quick

# Saida modo batch (JSON no stdout, logs no stderr):
{
  "sqli-login-bypass": "https://abc123.web-security-academy.net",
  "xss-reflected-html-nothing-encoded": "https://def456.web-security-academy.net",
  ...
}
```

O flag `--headed` e separado dos argumentos posicionais com `[a for a in sys.argv[1:] if not a.startswith("--")]`. Isto permite:
- `spinup.py <url> --headed` (modo headed para lab individual)
- `spinup.py --batch-subset quick --headed` (modo headed para batch)

---

## 7) `tests/evals/test_spinup.py` — Testes Unitarios

### Helper `_make_playwright_mock()`

```python
def _make_playwright_mock(instance_url: str = INSTANCE_URL):
    mock_lab_page = AsyncMock()
    mock_lab_page.url = instance_url

    async def _lab_page_value():
        return mock_lab_page

    mock_new_page_info = MagicMock()
    mock_new_page_info.value = _lab_page_value()  # coroutine awaitable

    mock_expect_page_cm = MagicMock()
    mock_expect_page_cm.__aenter__ = AsyncMock(return_value=mock_new_page_info)
    mock_expect_page_cm.__aexit__ = AsyncMock(return_value=False)
    ...
```

O ponto critico e `mock_new_page_info.value = _lab_page_value()`. Na API do Playwright, `EventInfo.value` e **awaitable** (retorna uma `asyncio.Future`). Se `value` for um `AsyncMock` atribuido directamente, `await new_page_info.value` falha com `TypeError: object AsyncMock can't be used in 'await' expression` em Python 3.12. A solucao e criar uma coroutine com `async def _lab_page_value()` e atribuir a instancia (`_lab_page_value()`), que e um objecto coroutine genuinamente awaitable.

### Estrutura de testes

```
TestCredentialErrors (5 testes)
  ├─ test_missing_both_vars_raises_auth_error
  ├─ test_missing_password_raises_auth_error
  ├─ test_missing_email_raises_auth_error
  ├─ test_error_message_names_both_env_vars
  └─ test_spinup_lab_propagates_auth_error

TestSessionPersistence (3 testes)
  ├─ test_existing_session_file_loaded_as_cookies
  ├─ test_no_session_file_skips_add_cookies
  └─ test_valid_session_skips_login

TestSpinupLabReturnsUrl (2 testes unit + 1 e2e)
  ├─ test_returns_instance_url
  ├─ test_selector_timeout_raises_timeout_error
  └─ test_real_spinup_returns_instance_url  [@pytest.mark.e2e]
```

### Testes de sessao — Como funciona a prova

```python
async def test_existing_session_file_loaded_as_cookies(self, tmp_path, monkeypatch):
    fake_cookies = [{"name": "session", "value": "tok123", "domain": "portswigger.net"}]
    session_file = tmp_path / ".portswigger_session.json"
    session_file.write_text(json.dumps(fake_cookies))

    with (
        patch("tests.evals.spinup.async_playwright", return_value=mock_pw_cm),
        patch("tests.evals.spinup.SESSION_FILE", session_file),
        patch("tests.evals.spinup._is_logged_in", AsyncMock(return_value=True)),
    ):
        await spinup_lab(LAB_URL)

    mock_context.add_cookies.assert_called_once_with(fake_cookies)
```

O teste patcha `SESSION_FILE` para um ficheiro temporario com cookies controlados, depois verifica que `context.add_cookies()` foi chamado exactamente com esses cookies. Prova que a logica de restauro de sessao funciona sem tocar no sistema de ficheiros real.

---

## 8) `tests/evals/test_spinup_e2e.py` — Testes E2E Reais

Quatro testes contra o site real PortSwigger. Requerem `PORTSWIGGER_EMAIL` e `PORTSWIGGER_PASSWORD` no ambiente.

```python
@pytest.mark.e2e
async def test_sqli_login_bypass_spinup_returns_instance_url():
    """🔁 spinup_lab returns a real *.web-security-academy.net URL for a known lab."""
    lab_url = _LABS_BY_ID["sqli-login-bypass"]["lab_url"]
    result = await spinup_lab(lab_url)
    assert result.startswith("https://")
    assert "web-security-academy.net" in result
    assert "portswigger.net" not in result
```

| Teste | AC Coberta | Infra Real |
|---|---|---|
| `test_sqli_login_bypass_spinup_returns_instance_url` | `spinup_lab` retorna URL `*.web-security-academy.net` | Browser Chromium + PortSwigger |
| `test_session_persisted_and_reused_on_second_spinup` | Sessao persistida; reexecucao nao repete login | Browser × 2 + ficheiro SESSION_FILE |
| `test_spinup_batch_quick_subset_returns_all_urls` | Batch para subset `quick` (4 labs) | Browser × 4 sequencial |
| `test_missing_credentials_raise_auth_error_before_browser_launch` | Falha de credenciais sem crash silencioso | Nenhuma (erro antes do browser) |

### Prova de reutilizacao de sessao (teste 2)

```python
# 1. Limpar sessao anterior
if SESSION_FILE.exists():
    SESSION_FILE.unlink()

# 2. Primeiro spinup → login + escrita de SESSION_FILE
result_1 = await spinup_lab(first_lab_url)
assert SESSION_FILE.exists()
mtime_before = SESSION_FILE.stat().st_mtime_ns

# 3. Segundo spinup imediato → sessao ainda valida
result_2 = await spinup_lab(second_lab_url)

# 4. SESSION_FILE NAO foi reescrito → _login nao foi chamado
mtime_after = SESSION_FILE.stat().st_mtime_ns
assert mtime_after == mtime_before
```

A prova e indirecta mas solida: `_save_session` so e chamado depois de `_login`. Se o mtime nao mudou, `_save_session` nao correu, logo `_login` nao correu. A sessao foi reutilizada.

---

## 9) CI — `.github/workflows/ci.yml`

### Passo adicional no job `unit`

```yaml
- name: Run eval unit tests (mocked, no credentials needed)
  run: >-
    pytest tests/evals/ -v --tb=short --timeout=120
    -m "not e2e" --junitxml=test-results/evals-unit.xml
```

`-m "not e2e"` exclui os 4 testes de `test_spinup_e2e.py` (marcados `@pytest.mark.e2e`) e executa os restantes 36 testes (26 de `test_portswigger_mvp.py` + 10 de `test_spinup.py`). Corre em cada PR, sem credenciais.

### Novo job `portswigger-spinup`

```yaml
portswigger-spinup:
  name: PortSwigger Spinup E2E
  runs-on: ubuntu-latest
  if: github.event_name == 'workflow_dispatch'
  steps:
    ...
    - name: Install Playwright Chromium
      run: playwright install chromium --with-deps

    - name: Run PortSwigger spinup E2E tests
      env:
        PORTSWIGGER_EMAIL: ${{ secrets.PORTSWIGGER_EMAIL }}
        PORTSWIGGER_PASSWORD: ${{ secrets.PORTSWIGGER_PASSWORD }}
      run: >-
        pytest tests/evals/test_spinup_e2e.py -v --tb=short --timeout=300
        -m e2e --junitxml=test-results/portswigger-spinup.xml
```

| Aspecto | Valor |
|---|---|
| Trigger | `workflow_dispatch` only (manual) — nao corre em cada PR |
| Servicos requeridos | Nenhum (sem PostgreSQL, Neo4j, ou Docker daemon) |
| Segredos | `PORTSWIGGER_EMAIL`, `PORTSWIGGER_PASSWORD` (adicionar em repo Settings → Secrets) |
| Tempo estimado | ~1 minuto (4 spinups sequenciais + login) |
| Efeito em `ci-pass` | **Nenhum** — `ci-pass` depende de `[lint, unit, integration, agent]`, nao de `portswigger-spinup` |

---

## Exemplo Completo: Fluxo de Batch Spinup

```bash
export PORTSWIGGER_EMAIL="user@example.com"
export PORTSWIGGER_PASSWORD="secret"

python tests/evals/spinup.py --batch-subset quick
```

```
[spinup] sqli-login-bypass ...          ← stderr
[spinup] sqli-login-bypass -> https://abc123.web-security-academy.net
[spinup] xss-reflected-html-nothing-encoded ...
[spinup] xss-reflected-html-nothing-encoded -> https://def456.web-security-academy.net
[spinup] auth-username-enum-different-responses ...
[spinup] auth-username-enum-different-responses -> https://ghi789.web-security-academy.net
[spinup] xxe-file-upload ...
[spinup] xxe-file-upload -> https://jkl012.web-security-academy.net
```

```json
{
  "sqli-login-bypass": "https://abc123.web-security-academy.net",
  "xss-reflected-html-nothing-encoded": "https://def456.web-security-academy.net",
  "auth-username-enum-different-responses": "https://ghi789.web-security-academy.net",
  "xxe-file-upload": "https://jkl012.web-security-academy.net"
}
```

O JSON sai no stdout (para pipe ou captura). Os logs de progresso vao para stderr (separados). O runner (US-047) consome este JSON para saber os URLs dos targets activos.

---

## Questoes Frequentes

### P: Porque e que o SESSION_FILE fica em `tests/evals/` e nao em `/tmp`?

**R:** Para persistir entre invocacoes do CLI (sessoes de desenvolvimento). Se estivesse em `/tmp`, cada terminal novo exigiria login. O ficheiro e ignorado pelo `.gitignore` implicitamente por nao ter extensao `.py`.

### P: O que acontece se o lab demorar mais de 30 segundos a arrancar?

**R:** `wait_for_url` lanca `PortSwiggerTimeoutError` com a URL actual para debug: `"Lab instance URL never resolved for ... Current URL: https://..."`. Isto permite distinguir entre timeout de rede e redirect inesperado (ex: login expirado mid-flight).

### P: Porque nao correr os 4 spinups do batch em paralelo (asyncio.gather)?

**R:** Dois motivos:
1. **Race condition no SESSION_FILE:** Dois `spinup_lab` em paralelo podem ler SESSION_FILE em simultâneo e depois ambos tentar escrever cookies novos (se a sessao expirar entretanto).
2. **Recursos:** Quatro instancias Chromium em paralelo consomem ~800 MB RAM num runner Ubuntu standard.

### P: O selector `.container-buttons-left a.button-orange` pode voltar a mudar?

**R:** Sim. O PortSwigger pode redesenhar a pagina. Se o selector mudar, `wait_for_selector` lanca `PortSwiggerTimeoutError` com a mensagem `"The lab page may not have loaded or the selector may have changed."` — que e o sinal para re-inspeccionar o DOM com o script de diagnostico usado durante a implementacao.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-045-PORTSWIGGER-MVP-DATASET-EXPLAINED]]
- [[EVAL-TARGETS]]
- [[LANGSMITH-EVALS-RESEARCH]]
- [[EXECUTION-FLOW]]
