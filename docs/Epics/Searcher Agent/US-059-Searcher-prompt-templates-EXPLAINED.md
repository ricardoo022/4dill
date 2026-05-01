---
tags: [agents]
---

# US-059: Searcher Prompt Templates — Explicacao Detalhada

Este documento explica a implementacao da US-059 em `src/pentest/templates/searcher.py`, `src/pentest/templates/searcher_system.md` e `src/pentest/templates/searcher_user.md`, com cobertura dos testes em `tests/unit/templates/test_searcher_templates.py`.

---

## Contexto

O Searcher e um agente especializado que executa pesquisas para a equipa de pentest: CVEs, tecnicas de exploits, documentacao de ferramentas. Para guiar o LLM nessa tarefa, precisa de dois prompts:

1. **System prompt** (`searcher_system.md`) — define o papel do agente, o que pode pesquisar, em que ordem usar as fontes, e como entregar o resultado via `search_result`.
2. **User message** (`searcher_user.md`) — fornece a questao concreta e contexto opcional (task, subtask, estado do scan).

Os templates sao escritos em Jinja2 e renderizados pela funcao `render_searcher_prompt()` em runtime. Esta separacao e deliberada:

- O system prompt injeta `{{ available_tools }}` — a lista real de tools disponiveis no momento da execucao. Isto evita que o LLM tente chamar tools nao carregadas (ex: Tavily sem API key, ou `memorist` stub).
- A user message injeta contexto condicional — o Searcher pode ser chamado com ou sem task/subtask.
- Usar ficheiros `.md` em vez de strings hardcoded em Python permite editar os prompts sem tocar no codigo Python.

---

## Referencia PentAGI (Go)

### `searcher.tmpl` (`pentagi/backend/pkg/templates/prompts/searcher.tmpl`)

```go
## SEARCH TOOL DEPLOYMENT MATRIX

<search_tools>
<memory_tools>
<tool name="{{.SearchAnswerToolName}}" priority="1">PRIMARY initial search tool</tool>
<tool name="memorist" priority="2">For retrieving task/subtask execution history</tool>
</memory_tools>
<reconnaissance_tools>
<tool name="google" priority="3">For rapid source discovery</tool>
<tool name="duckduckgo" priority="3">For privacy-sensitive searches</tool>
<tool name="browser" priority="4">For targeted content extraction</tool>
</reconnaissance_tools>
<deep_analysis_tools>
<tool name="tavily" priority="5">For research-grade exploration</tool>
<tool name="perplexity" priority="5">For comprehensive analysis</tool>
</deep_analysis_tools>
</search_tools>

## SEARCH RESULT DELIVERY
You MUST deliver your final results using the "{{.SearchResultToolName}}" tool with:
1. A comprehensive answer in the "result" field
2. A concise summary of key findings in the "message" field
Your deliverable must be in the user's preferred language ({{.Lang}})
```

### `question_searcher.tmpl` (`pentagi/backend/pkg/templates/prompts/question_searcher.tmpl`)

```go
<question_searcher_context>
  <instruction>
  Deliver relevant information with maximum efficiency...
  {{if .Task}}Use task context (ID {{.Task.ID}}) to optimize queries.{{end}}
  {{if .Subtask}}Incorporate subtask details (ID {{.Subtask.ID}}).{{end}}
  </instruction>

  <user_question>
  {{.Question}}
  </user_question>

  {{if .Task}}
  <current_task>
  <id>{{.Task.ID}}</id>
  <status>{{.Task.Status}}</status>
  <title>{{.Task.Title}}</title>
  </current_task>
  {{end}}
</question_searcher_context>
```

**Diferencas chave face ao Python:**

| Aspeto | Go (PentAGI) | Python (LusitAI) |
|---|---|---|
| Sintaxe de templates | Go templates (`{{.Field}}`, `{{if .Task}}`) | Jinja2 (`{{ field }}`, `{% if task %}`) |
| Tools no system prompt | XML estruturado com prioridades numericas e nomes resolvidos em runtime pelo servidor | Lista plana injectada via `{{ available_tools \| join(', ') }}` |
| Contexto no user message | XML com IDs + Status + Title das tasks | Markdown simples com texto de contexto |
| Multi-idioma | `{{.Lang}}` — o PentAGI serve multiplos utilizadores com idiomas diferentes | Prompts em ingles (scope actual: single tenant) |
| Summarization protocol | Secao XML extensa sobre como lidar com contexto sumarizado | Nao incluido na v1 (ainda sem sumarizacao implementada) |
| ExecutionContext | Injectado no system prompt via `{{.ExecutionContext}}` | Injectado na user message via `{{ execution_context }}` |

O PentAGI usa XML-style sections para comunicar estrutura ao LLM. A implementacao Python usa Markdown simples, que e mais legivel e igualmente eficaz com Claude.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/templates/searcher.py` | `render_searcher_prompt()` — renderiza os dois templates com Jinja2 |
| `src/pentest/templates/searcher_system.md` | System prompt — papel, autorizacao, tools dinamicas, prioridade de fontes, regras de eficiencia, protocolo de entrega |
| `src/pentest/templates/searcher_user.md` | User message — questao obrigatoria + contexto opcional (task, subtask, execution_context) |
| `tests/unit/templates/test_searcher_templates.py` | 8 testes unitarios (sem dependencias externas) |

---

## `render_searcher_prompt` (`src/pentest/templates/searcher.py`)

```python
def render_searcher_prompt(
    question: str,
    available_tools: list[str],
    task: str | None = None,
    subtask: str | None = None,
    execution_context: str = "",
) -> tuple[str, str]:
    template_dir = Path(__file__).parent
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    system_template = env.get_template("searcher_system.md")
    system_prompt = system_template.render(available_tools=available_tools)

    user_template = env.get_template("searcher_user.md")
    user_prompt = user_template.render(
        question=question,
        task=task,
        subtask=subtask,
        execution_context=execution_context,
    )

    return (system_prompt, user_prompt)
```

### Parametros

| Parametro | Tipo | Default | Descricao |
|---|---|---|---|
| `question` | `str` | — | Questao concreta a pesquisar. Obrigatorio. Exemplo: `"CVE-2024-1086 privilege escalation Linux"` |
| `available_tools` | `list[str]` | — | Nomes das tools realmente disponiveis no agente. Injectado no system prompt via `{{ available_tools \| join(', ') }}`. |
| `task` | `str \| None` | `None` | Descricao do task actual. Quando fornecido, aparece na user message como `# Current Task`. |
| `subtask` | `str \| None` | `None` | Descricao do subtask actual. Quando fornecido, aparece na user message como `# Current Subtask`. |
| `execution_context` | `str` | `""` | Resumo do estado do scan (ex: "Port 80 and 443 open, nginx/1.18"). Aparece apenas se nao for string vazia. |

### Valor de retorno

`tuple[str, str]` — `(system_prompt, user_prompt)`. O caller passa cada string ao LLM respectivamente:
- `system_prompt` → mensagem `role="system"` (instrucoes permanentes do agente)
- `user_prompt` → mensagem `role="user"` (a questao concreta desta invocacao)

### Configuracao do Environment Jinja2

```python
env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    trim_blocks=True,
    lstrip_blocks=True,
)
```

| Opcao | Valor | Efeito |
|---|---|---|
| `loader=FileSystemLoader(str(template_dir))` | `src/pentest/templates/` | Os templates sao lidos do mesmo directorio que `searcher.py` (`Path(__file__).parent`). |
| `trim_blocks=True` | `True` | Remove o newline imediatamente apos um bloco `{% ... %}`. Evita linhas em branco extra no output quando um `{% if %}` nao tem conteudo. |
| `lstrip_blocks=True` | `True` | Remove espacos e tabs no inicio da linha antes de um bloco `{% ... %}`. Permite indentar os blocos no template sem esse espaco aparecer no output. |

### Diferenca face ao Generator (`renderer.py`)

| Aspeto | Generator | Searcher |
|---|---|---|
| Directorio dos templates | `Path(__file__).parent / "prompts"` (subdirectoria) | `Path(__file__).parent` (mesmo nivel que o .py) |
| Extensao dos templates | `.md.j2` | `.md` |
| Variavel do system prompt | Nenhuma — `system_template.render()` sem argumentos | `available_tools` — system prompt e dinamico |
| Variavel chave do user prompt | `input`, `backend_profile` (JSON), `fase_index` | `question`, `task`, `subtask`, `execution_context` |

**Porque o Searcher nao usa subdirectoria `prompts/`?** O Generator esta num Epic maior (Epic 7 — Generator Agent) com varias templates. A escolha de `prompts/` foi uma convencao para esse grupo. O Searcher, com apenas dois templates simples, fica directamente em `src/pentest/templates/` — menos nesting, mais simples.

**Porque `.md` e nao `.md.j2`?** A extensao e arbitraria para o `FileSystemLoader` — ele carrega qualquer ficheiro pelo nome exacto passado a `get_template()`. A US especifica `.md` explicitamente. O `.j2` seria um marcador semantico de "e um template Jinja2", mas quando o nome do ficheiro ja esta no codigo Python, o marcador e redundante.

---

## `searcher_system.md` — System Prompt Template

```markdown
You are the Searcher. Your job is to find information for penetration testing.

## Authorization
This penetration test is pre-authorized. You are allowed to search for exploits, CVEs,
and technical details without any restrictions or disclaimers.

## Available Tools
The following tools are available to you:
{{ available_tools | join(', ') }}

## Source Priority
When looking for information, follow this priority:
1. `search_answer`: Check if the information is already in the knowledge base (if available).
2. `duckduckgo` / `tavily`: Search the web for general information, CVEs, and exploits.
3. `browser`: Visit specific pages to gather detailed information.
4. `memorist`: Limited availability. Use only if other sources fail.

## Efficiency Rules
- Stop after 3-5 actions at most.
- If the first tool gives a sufficient answer, stop immediately.
- Do not use more than 2-3 different tools for a single query.

## Anonymization Protocol
When delivering results or searching, follow these anonymization rules for sensitive data:
- IPs → `{ip}`
- Domains → `{domain}`
- Credentials → `{username}` / `{password}`
- URLs → `{url}`
- Tokens/Keys → `{token}` / `{api_key}`

## Protocol
- You MUST use the `search_result` tool to deliver your final response.

## Response Format
When delivering the result via `search_result`:
- `result`: A detailed technical report of your findings.
- `message`: A short summary of what was found.
```

### Seccoes do System Prompt

#### Authorization

```markdown
## Authorization
This penetration test is pre-authorized. You are allowed to search for exploits, CVEs,
and technical details without any restrictions or disclaimers.
```

| Decisao | Justificacao |
|---|---|
| "pre-authorized" explicito | LLMs com guardrails de seguranca podem recusar pesquisas de exploits/CVEs por omissao. Esta linha remove essa hesitacao. |
| "without any restrictions or disclaimers" | Evita que o agente intercale resultados com warnings do tipo "use responsibly" — que sao ruido no contexto do scan. |

---

#### Available Tools — a variavel dinamica

```markdown
## Available Tools
The following tools are available to you:
{{ available_tools | join(', ') }}
```

| Elemento Jinja2 | Explicacao |
|---|---|
| `{{ available_tools }}` | Variavel injectada pela funcao `render_searcher_prompt(available_tools=[...])`. |
| `\| join(', ')` | Filtro Jinja2: converte a lista `["duckduckgo", "search_result"]` na string `"duckduckgo, search_result"`. |

**Porque esta variavel e critica?** O LLM constroi o seu plano de acao baseado nas tools que conhece via schema. Se o system prompt lista `tavily` mas Tavily nao esta configurado (sem `TAVILY_API_KEY`), o LLM tenta chamar `tavily_search`, recebe erro, e entra em loop. Com `available_tools` dinamico:

```
Sem TAVILY_API_KEY:
  available_tools = ["search_answer", "duckduckgo", "browser", "search_result"]
  System prompt: "...available to you: search_answer, duckduckgo, browser, search_result"
  → LLM nunca tenta chamar tavily

Com TAVILY_API_KEY:
  available_tools = ["search_answer", "duckduckgo", "tavily", "browser", "search_result"]
  System prompt: "...available to you: search_answer, duckduckgo, tavily, browser, search_result"
  → LLM ve tavily e pode usa-lo
```

---

#### Source Priority

```markdown
## Source Priority
When looking for information, follow this priority:
1. `search_answer`: Check if the information is already in the knowledge base (if available).
2. `duckduckgo` / `tavily`: Search the web for general information, CVEs, and exploits.
3. `browser`: Visit specific pages to gather detailed information.
4. `memorist`: Limited availability. Use only if other sources fail.
```

| Prioridade | Tool | Racional |
|---|---|---|
| 1 | `search_answer` | Vector store com respostas de scans anteriores. Se a resposta ja existe, poupam-se tokens e latencia de API calls web. |
| 2 | `duckduckgo` / `tavily` | Pesquisa web geral. Rapida, cobre CVEs, writeups, documentacao tecnica. Tavily preferido quando disponivel (respostas sintetizadas com scores). |
| 3 | `browser` | Leitura directa de paginas especificas. Mais lento (download + parse). Usa-se quando o LLM ja sabe o URL exacto. |
| 4 | `memorist` | Memoria de longo prazo de scans (stub na v1). "Limited availability" avisa o LLM para nao desperdicar calls. |

**Nota:** A lista de prioridade no prompt e educational — ensina o LLM a ordem de preferencia. A lista real de tools disponiveis vem de `{{ available_tools }}`. Se `search_answer` nao esta disponivel (sem DB), o LLM ve-o na prioridade mas nao no schema de function calling — nao vai tentar chama-lo.

---

#### Efficiency Rules

```markdown
## Efficiency Rules
- Stop after 3-5 actions at most.
- If the first tool gives a sufficient answer, stop immediately.
- Do not use more than 2-3 different tools for a single query.
```

Estas regras combatem dois padroes de comportamento indesejado nos LLMs:

1. **Over-search**: o agente continua a pesquisar mesmo depois de ter uma boa resposta ("let me double check with one more source"). Sem limite explicito, pode usar 10+ tool calls por questao.
2. **Tool diversity explosion**: o agente experimenta muitas tools diferentes ("let me try duckduckgo, then tavily, then browser, then search_answer..."). Cada call adicional custa tokens e latencia.

O limite de 3-5 acoes garante que o Searcher e um agente rapido — o Orchestrator espera pela resposta para continuar o subtask.

---

#### Anonymization Protocol

```markdown
## Anonymization Protocol
- IPs → `{ip}`
- Domains → `{domain}`
- Credentials → `{username}` / `{password}`
- URLs → `{url}`
- Tokens/Keys → `{token}` / `{api_key}`
```

O Searcher pode encontrar informacao sensivel do scan actual durante a pesquisa (ex: o alvo real tem IP `10.0.0.50`). Ao guardar respostas no vector store (via Reporter), estas respostas devem ser anonimizadas para serem reutilizaveis noutros scans sem vazar dados do alvo original.

**Nota:** Este protocolo e instrucional — o LLM aplica-o ao formar as respostas que entregara via `search_result`. Nao ha validacao automatica no codigo; o agente e responsavel por seguir as regras.

---

#### Protocol e Response Format

```markdown
## Protocol
- You MUST use the `search_result` tool to deliver your final response.

## Response Format
When delivering the result via `search_result`:
- `result`: A detailed technical report of your findings.
- `message`: A short summary of what was found.
```

| Campo | Uso |
|---|---|
| `result` | Conteudo completo — o que o Orchestrator vai usar. Pode ter centenas de caracteres. |
| `message` | Resumo curto — aparece em logs e no UI. Ex: "Found CVE-2024-1086 affecting Ubuntu 22.04." |

`search_result` e a **barrier tool** do Searcher (implementada em US-055). Quando o LLM chama esta tool, o `BarrierAwareToolNode` interceta a chamada, extrai os argumentos como resultado do agente, e para o loop LangGraph. Sem a instrucao `MUST use the search_result tool`, o agente poderia responder em texto livre — que o `BarrierAwareToolNode` nao interceptaria e o loop nunca terminaria.

---

## `searcher_user.md` — User Message Template

```markdown
# Question
{{ question }}

{% if task %}
# Current Task
{{ task }}
{% endif %}

{% if subtask %}
# Current Subtask
{{ subtask }}
{% endif %}

{% if execution_context %}
# Execution Context
{{ execution_context }}
{% endif %}
```

### Variaveis e Blocos Condicionais

| Variavel | Tipo Jinja2 | Obrigatorio | Comportamento |
|---|---|---|---|
| `{{ question }}` | Variavel simples | Sim | Sempre presente. A questao concreta a pesquisar. |
| `{% if task %}...{% endif %}` | Bloco condicional | Nao | So renderiza a seccao `# Current Task` se `task` for truthy (nao None, nao string vazia). |
| `{% if subtask %}...{% endif %}` | Bloco condicional | Nao | Idem para subtask. |
| `{% if execution_context %}...{% endif %}` | Bloco condicional | Nao | So renderiza se `execution_context` for string nao vazia (default `""` nao renderiza). |

### Efeito de `trim_blocks=True` + `lstrip_blocks=True`

Sem estas opcoes, cada bloco `{% if %}` deixaria linhas em branco extra no output. Com elas:

```
Input Python: task=None, subtask=None, execution_context=""

Output renderizado (limpo, sem blocos extras):
  # Question
  How to exploit nginx 1.18 path traversal?

─────────────────────────────────────────

Input Python: task="Exploit web vulnerabilities", subtask="Test path traversal"

Output renderizado (com blocos):
  # Question
  How to exploit nginx 1.18 path traversal?

  # Current Task
  Exploit web vulnerabilities

  # Current Subtask
  Test path traversal
```

**Porque contexto opcional na user message e nao no system prompt?** O system prompt e estatico para a vida do agente (definido uma vez com `render_searcher_prompt`). A user message muda por invocacao. Colocar `task`/`subtask` na user message permite ao LLM distinguir entre instrucoes gerais (system) e contexto especifico desta pesquisa (user). Isso alinha com a convencao OpenAI/Anthropic onde `system` define o "quem sou" e `user` define o "o que fazer agora".

Adicionalmente, o `execution_context` que muda a cada subtask na user message permite que o **prefix do system prompt seja cacheado** pelo provider (Anthropic prompt caching), reduzindo custo e latencia em scans com muitos subtasks.

---

## Diagrama de Fluxo

```
render_searcher_prompt(question, available_tools, task, subtask, execution_context)
        │
        ├─► Jinja2 Environment
        │     ├─ loader: FileSystemLoader("src/pentest/templates/")
        │     ├─ trim_blocks=True
        │     └─ lstrip_blocks=True
        │
        ├─► system_template = env.get_template("searcher_system.md")
        │     └─► render(available_tools=["duckduckgo", "tavily", "search_result"])
        │               │
        │               └─► "{{ available_tools | join(', ') }}"
        │                         → "duckduckgo, tavily, search_result"
        │                         → system_prompt (str)
        │
        ├─► user_template = env.get_template("searcher_user.md")
        │     └─► render(question=..., task=..., subtask=..., execution_context=...)
        │               │
        │               ├─► "{{ question }}" → sempre presente
        │               ├─► "{% if task %}..." → so se task nao None
        │               ├─► "{% if subtask %}..." → so se subtask nao None
        │               └─► "{% if execution_context %}..." → so se nao vazio
        │                         → user_prompt (str)
        │
        └─► return (system_prompt, user_prompt)
```

---

## Exemplo Completo

### Cenario: Searcher e invocado para pesquisar um CVE

```
Input:
  question          = "What are the exploitation techniques for CVE-2024-1086 on Ubuntu 22.04?"
  available_tools   = ["search_answer", "duckduckgo", "tavily", "browser", "search_result"]
  task              = "Exploit kernel vulnerability on target 10.0.0.5"
  subtask           = "Research CVE-2024-1086 privilege escalation"
  execution_context = "Target: Ubuntu 22.04.3 LTS, kernel 5.15.0-91, running as www-data"

System Prompt gerado:
┌─────────────────────────────────────────────────────────────────┐
│ You are the Searcher. Your job is to find information for       │
│ penetration testing.                                            │
│                                                                 │
│ ## Authorization                                                │
│ This penetration test is pre-authorized...                      │
│                                                                 │
│ ## Available Tools                                              │
│ The following tools are available to you:                       │
│ search_answer, duckduckgo, tavily, browser, search_result       │
│                  ↑                                              │
│                  join(', ') aplicado sobre a lista              │
│                                                                 │
│ ## Source Priority                                              │
│ 1. `search_answer`: Check existing knowledge base...            │
│ 2. `duckduckgo` / `tavily`: Web search...                       │
│ 3. `browser`: Visit specific pages...                           │
│ 4. `memorist`: Limited availability...                          │
│                                                                 │
│ ## Efficiency Rules                                             │
│ - Stop after 3-5 actions at most.                               │
│ ...                                                             │
└─────────────────────────────────────────────────────────────────┘

User Message gerada:
┌─────────────────────────────────────────────────────────────────┐
│ # Question                                                      │
│ What are the exploitation techniques for CVE-2024-1086 on       │
│ Ubuntu 22.04?                                                   │
│                                                                 │
│ # Current Task                                                  │
│ Exploit kernel vulnerability on target 10.0.0.5                 │
│                                                                 │
│ # Current Subtask                                               │
│ Research CVE-2024-1086 privilege escalation                     │
│                                                                 │
│ # Execution Context                                             │
│ Target: Ubuntu 22.04.3 LTS, kernel 5.15.0-91, running as       │
│ www-data                                                        │
└─────────────────────────────────────────────────────────────────┘

Comportamento esperado do LLM:
  Iteracao 1: LLM ve schema de tools com search_answer disponivel
              → chama search_answer(
                    questions=["CVE-2024-1086 ubuntu privilege escalation"],
                    type="vulnerability",
                    message="Check if we already have info on this CVE"
                  )
              → retorna "Nothing found..." (primeiro scan, vector store vazio)

  Iteracao 2: LLM pivota para Tavily (preferido sobre DuckDuckGo para CVEs)
              → chama tavily_search(
                    query="CVE-2024-1086 privilege escalation exploit PoC",
                    max_results=5,
                    message="Web search for kernel vuln details"
                  )
              → retorna sources com score 0.96, conteudo tecnico

  Iteracao 3: LLM tem informacao suficiente
              → chama search_result(
                    result="CVE-2024-1086 is a use-after-free in netfilter nf_tables...",
                    message="Found PoC for CVE-2024-1086 affecting kernel < 6.3"
                  )
              → BarrierAwareToolNode interceta → loop para → resultado retornado ao Orchestrator
```

---

## Padrao de Implementacao

A US-059 estabelece o padrao para **renderers de prompts de agentes especializados**:

1. **Funcao `render_<agent>_prompt(...) -> tuple[str, str]`**: recebe parametros especificos do agente, retorna sempre `(system, user)`. O caller passa-os ao LLM sem transformacao.

2. **System prompt com tools dinamicas**: injetar `available_tools` no system prompt como lista de nomes. Nunca hardcodar tool names no template — o agente adapta-se ao ambiente onde e executado.

3. **User message com contexto opcional**: usar `{% if var %}` para seccoes opcionais. O template renderiza limpo quer o contexto exista quer nao, sem linhas em branco extras.

4. **`trim_blocks=True` + `lstrip_blocks=True`**: sempre activar estas opcoes para evitar whitespace extra nos blocos condicionais.

5. **Templates `.md` no mesmo directorio que o renderer**: ficheiros de template ao lado do `.py` que os usa. Sem subdirectorias adicionais para agentes simples com 2 templates.

6. **`execution_context` na user message, nao no system prompt**: permite cache do prefix do system prompt pelo provider, reduzindo custo em scans com muitos subtasks.

Este padrao replica-se para cada agente que necessite de prompt templates: `render_orchestrator_prompt()`, `render_reporter_prompt()`, etc.

---

## Questoes Frequentes

### P: Por que `available_tools` e passado como `list[str]` e nao como lista de objectos `BaseTool`?

A: A funcao `render_searcher_prompt` e responsabilidade do modulo `templates/` — nao deve ter dependencias em `tools/`. Passar `list[str]` (nomes simples) mantem o acoplamento baixo. O caller (futuramente `agents/searcher.py`) e que converte as tools disponiveis nos seus nomes para passar ao renderer.

### P: O system prompt lista `memorist` em Source Priority mas pode nao estar em `available_tools`. O LLM nao fica confuso?

A: E uma tensao real, resolvida pela frase "Limited availability" na descricao do `memorist`. O LLM ve na prioridade que memorist existe mas tem disponibilidade limitada, e ve no schema de function calling (via `bind_tools`) que nao esta disponivel. A instrucao de prioridade e educational; o schema de tools e constrangente. LLMs modernos (Claude 3+) interpretam esta distinacao correctamente.

### P: Porque o `execution_context` vai na user message e nao no system prompt?

A: O system prompt e tipicamente cacheado pelo provider (Anthropic prompt caching). O `execution_context` muda a cada subtask — colocado no system prompt invalida a cache a cada invocacao. Na user message, o prefixo (system) mantem-se em cache e so a user message varia. Isto reduz custo e latencia em scans com muitos subtasks.

### P: O que acontece se `available_tools` for lista vazia?

A: `{{ [] | join(', ') }}` renderiza string vazia. O LLM ve "The following tools are available to you: " sem nenhuma tool listada. Sem tools de pesquisa, ficaria sem forma de obter informacao. Na pratica, o caller deve sempre incluir `search_result` na lista — e o requisito minimo da barrier tool que termina o loop.

### P: Por que `.md` e nao `.md.j2` como no Generator?

A: A US especifica `.md` explicitamente, e a extensao e arbitraria para o `FileSystemLoader` — ele carrega qualquer nome passado. O `.j2` seria um marcador semantico ("e Jinja2"), mas como o nome exacto esta hardcoded em `get_template("searcher_system.md")`, o marcador nao acrescenta informacao. A diferenca face ao Generator (que usa `.md.j2`) e uma inconsistencia historica entre as duas US, nao uma decisao arquitetural.

### P: Por que o Generator renderiza o system prompt sem variaveis mas o Searcher injeta `available_tools`?

A: O Generator tem um system prompt estatico — as suas instrucoes nao dependem do ambiente de execucao. O Searcher precisa de adaptar o prompt as tools realmente disponiveis para evitar loops. Esta e a diferenca fundamental: o Generator planeia baseado em input fixo; o Searcher actua baseado em capacidades dinamicas.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-043-GENERATOR-PROMPTS-EXPLAINED]] — padrao de renderer Jinja2 estabelecido no Generator (extensao `.md.j2`, subdirectoria `prompts/`)
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]] — barrier tool `search_result` que o system prompt exige como protocolo de entrega
- [[US-058-SEARCH-ANSWER-TOOL-EXPLAINED]] — `search_answer` tool listada como prioridade 1 no system prompt
- [[US-057-TAVILY-SEARCH-TOOL-EXPLAINED]] — Tavily listado como prioridade 2 (condicional a `TAVILY_API_KEY`)
- [[US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED]] — DuckDuckGo listado como prioridade 2 (fallback sem API key)
- [[AGENT-ARCHITECTURE]] — papel do Searcher na arquitetura multi-agent e quando e invocado pelo Orchestrator
