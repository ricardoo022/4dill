---
tags: [agents, architecture]
---

# US-043: Generator Prompt Templates — Explicacao Detalhada

Este documento explica o modulo de **Renderizacao de Prompts para o Generator Agent** implementado em `src/pentest/templates/`. O modulo fornece templates Jinja2 estruturados e um renderer que gera prompts do sistema e do utilizador, garantindo que o Generator agent receba instrucoes claras, contexto estruturado, e barreiras explícitas para a acao.

---

## Contexto: Por que Templates Jinja2?

### O Problema: Prompts Ad-Hoc e Inconsistentes

O Generator agent e a "mente planeadora" do SecureDev PentestAI. Ele deve:

1. Compreender a meta do utilizador (ex: "scan https://example.com")
2. Analisar o perfil do backend (FASE 0 - resultado da etapa anterior)
3. Consultar as fases disponiveis (FASE 1-N)
4. Planear um ataque estruturado em subtarefas

Se construissemos o prompt dinamicamente com string concatenation ou f-strings:

```python
# Problema: Dificil manter, propenso a erros
system = f"You are a Generator agent. Tools: {tools_list}."
user = f"Goal: {goal}\nProfile: {profile_json}"
```

**Limitacoes:**
- Logica de prompt espalhada em multiplos ficheiros
- Dificil de revisar ou atualizar instruções
- Sem separacao clara entre "What" (instrucoes) e "Data" (contexto)
- Impossivel reutilizar se o frontend tambem precisar dos prompts

### A Solucao: Templates Jinja2 com Renderer

Jinja2 oferece:

| Caracteristica | Beneficio |
|---|---|
| **Centralizacao** | Prompts vivem em ficheiros `.j2` dedicados, nao espalhados em codigo Python |
| **Separacao de Concerns** | Template contem instrucoes fixas; renderer fornece dados dinamicos |
| **Condicional Rendering** | `{% if execution_context %}...{% endif %}` permite prompts adaptados ao estado |
| **Iteracao Rapida** | Atualizar instruções nao requer rebuild ou restart de servico |
| **Auditoria** | Historico de commit mostra exatamente o que mudou nas instrucoes |

### Arquitetura de Renderizacao

```
render_generator_prompt(input_text, backend_profile, fase_index, execution_context)
├─ Setup Jinja2 Environment
│  ├─ Loader: FileSystemLoader → src/pentest/templates/prompts/
│  └─ Opcoes: trim_blocks=True (remove linhas em branco apos tags)
├─ Render generator_system.md.j2 (sem variaveis)
│  └─ Return: system_prompt (str, fixed instructions)
├─ Render generator_user.md.j2 (com 4 variaveis)
│  ├─ input: Goal do utilizador
│  ├─ backend_profile: Dicionario Python (renderizado como JSON)
│  ├─ fase_index: String com lista de fases disponiveis
│  └─ execution_context: Contexto anterior (condicional)
└─ Return: tuple (system_prompt, user_prompt)
```

Exemplo de Fluxo:

```python
# Entrada
system, user = render_generator_prompt(
    input_text="scan https://target.local",
    backend_profile={"target": "...", "tech": ["Django"]},
    fase_index="## Fases...\n- fase-1: Recon\n...",
    execution_context=""  # Primeira analise
)

# Saida
system = """# Generator Agent System Prompt
You are the Generator agent of SecureDev PentestAI.
[... 30 linhas de instrucoes ...]
- Maximum 15 subtasks per plan
"""

user = """# Generator Agent User Message
## Goal
scan https://target.local

## FASE 0 Backend Profile
{"target": "https://target.local", "tech": ["Django"]}

## Available Testing Phases
## Fases...
- fase-1: Recon

## Execution Context
This is the first analysis phase for this target.
"""

# Retorna tuple (sistema, utilizador)
```

---

## Estrutura dos Templates

### generator_system.md.j2: Instrucoes Fixas

**Localizacao:** `src/pentest/templates/prompts/generator_system.md.j2`

Este template define o **papel** do Generator e as **regras obrigatorias** que deve seguir.

```markdown
# Generator Agent System Prompt

You are the Generator agent of SecureDev PentestAI.

## Your Role

You are the primary planner for penetration testing operations...

## Available Tools

- **terminal**: Execute commands in a sandboxed environment
- **browser**: Interact with the target web interface
- **searcher**: Query the knowledge base for vulnerabilities
- **memorist**: Store and retrieve findings

## Requirements

- Maximum 15 subtasks per plan
- Each subtask MUST include:
  - `title`: A clear, actionable name
  - `description`: Detailed instructions
  - `fase`: A valid fase string (e.g., "scan-fase-1")
```

#### Elementos Criticos

| Elemento | Proposito | Impacto |
|---|---|---|
| **Role Definition** | "You are the Generator agent of SecureDev PentestAI" | Estabelece identidade e contexto de autoridade |
| **Tool Inventory** | Lista explícita de 4 ferramentas disponiveis | Impede que o agente invente ferramentas inexistentes |
| **15-Subtask Limit** | "Maximum 15 subtasks per plan" | Controla tamanho do plano; impede explosao de complexidade |
| **Subtask Structure** | Requer `title`, `description`, `fase` | Garante output estruturado e processavel |
| **subtask_list Barrier** | "Submit your plan using the subtask_list tool when complete" | Forca o agente a chamar tool específica para validar output |

#### Por que Nao Usar Prompt Dinamico?

Se injetassemos instrucoes no prompt do utilizador:

```python
# Antipattern
user_prompt = f"You have 15 subtasks max. Available tools: {tools_json}."
```

**Problemas:**
- Difícil de manter sincronismo entre sistema e utilizador
- System message e mais forte (OpenAI/Anthropic prioriza system message)
- Dados (tools_json) misturados com instrucoes

**Solucao (atual):**
- System message fixo contem TODAS as instrucoes
- User message contem SO dados (goal, profile, phases)

### generator_user.md.j2: Contexto Dinamico

**Localizacao:** `src/pentest/templates/prompts/generator_user.md.j2`

Este template assembla **dados especificos do target e da sessao** para cada invocacao.

```markdown
# Generator Agent User Message

## Goal

{{ input }}

## FASE 0 Backend Profile

The following information was gathered during initial reconnaissance:

```json
{{ backend_profile }}
```

## Available Testing Phases

{{ fase_index }}

## Execution Context

{% if execution_context %}
Previous findings and context:

{{ execution_context }}
{% else %}
This is the first analysis phase for this target.
{% endif %}
```

#### Variaveis Injetadas

| Variavel | Tipo | Origem | Exemplo |
|---|---|---|---|
| `{{ input }}` | str | Utilizador | "scan https://example.com for vulnerabilities" |
| `{{ backend_profile }}` | dict (renderizado como JSON) | FASE 0 Scanner | `{"target": "...", "tech": ["Django"], "ports": [80, 443]}` |
| `{{ fase_index }}` | str | US-042 Skill Loader | "Fases disponíveis:\n- fase-1: Recon\n- fase-3: RLS..." |
| `{{ execution_context }}` | str | Historico da sessao | "Port 443 weak SSL. Previous findings: CVE-2023-1234" |

#### Logica Condicional: execution_context

```jinja
{% if execution_context %}
Previous findings and context:

{{ execution_context }}
{% else %}
This is the first analysis phase for this target.
{% endif %}
```

**Fluxo:**

| Cenario | Resultado |
|---|---|
| Primeira analise (execution_context = "") | Mostra: "This is the first analysis phase for this target." |
| Analise posterior (execution_context = "Port 443 weak SSL...") | Mostra: "Previous findings and context:\n\nPort 443 weak SSL..." |

**Proposito:** Adaptar o prompt ao estado da sessao. Se e a primeira, o agente comeca do zero. Se ha contexto anterior, reutiliza encontrados.

#### Fluxo de Dados: Backend Profile

O `backend_profile` e um dicionario Python que sera renderizado como JSON:

```python
# Input ao renderer
backend_profile = {
    "target": "https://api.example.com",
    "technologies": ["FastAPI", "PostgreSQL"],
    "detected_ports": [80, 443, 5432],
    "headers": {"Server": "FastAPI"}
}

# Rendered no template (via Jinja2 automatic JSON conversion)
```json
{
    "target": "https://api.example.com",
    "technologies": ["FastAPI", "PostgreSQL"],
    "detected_ports": [80, 443, 5432],
    "headers": {"Server": "FastAPI"}
}
```
```

---

## O Renderer: render_generator_prompt()

**Localizacao:** `src/pentest/templates/renderer.py`

### Assinatura

```python
def render_generator_prompt(
    input_text: str,
    backend_profile: dict,
    fase_index: str,
    execution_context: str = "",
) -> tuple[str, str]:
    """Render generator system and user prompts using Jinja2 templates.

    Args:
        input_text: User's goal (e.g., "scan https://example.com")
        backend_profile: JSON representation of FASE 0 results as dict
        fase_index: The output from US-042, describing available phases
        execution_context: Optional previous context from earlier analysis

    Returns:
        Tuple of (system_prompt_str, user_prompt_str)
    """
```

### Implementacao: Passo a Passo

#### Passo 1: Setup Jinja2 Environment

```python
template_dir = Path(__file__).parent / "prompts"
env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    trim_blocks=True,
    lstrip_blocks=True,
)
```

| Configuracao | Significado | Beneficio |
|---|---|---|
| `FileSystemLoader(template_dir)` | Carrega templates de disco | Templates vivem em ficheiros, nao hardcoded |
| `trim_blocks=True` | Remove linhas em branco apos tags de bloco | Prompts mais limpos, sem linhas em branco extra |
| `lstrip_blocks=True` | Remove indentacao esquerda de tags | Indentacao em template nao afeta output |

**Exemplo de trim_blocks:**

```jinja
{% if execution_context %}
Previous findings:
{{ execution_context }}
{% endif %}
More text here
```

Sem `trim_blocks`: Extra newline apos `{% endif %}` aparecia no output.
Com `trim_blocks`: Output e limpo.

#### Passo 2: Renderizar System Prompt

```python
system_template = env.get_template("generator_system.md.j2")
system_prompt = system_template.render()
```

- Nao passa variaveis (nao ha `{{ var }}` no template)
- Retorna string com instrucoes fixas
- Identico para cada invocacao

#### Passo 3: Renderizar User Prompt

```python
user_template = env.get_template("generator_user.md.j2")
user_prompt = user_template.render(
    input=input_text,
    backend_profile=backend_profile,
    fase_index=fase_index,
    execution_context=execution_context,
)
```

- Passa 4 variaveis ao template
- Jinja2 substitui `{{ var }}` pelos valores
- Condicionales (`{% if %}`) sao processadas

#### Passo 4: Retornar Tuple

```python
return (system_prompt, user_prompt)
```

**Por que tuple e nao dict?**

| Opcao | Pros | Contras |
|---|---|---|
| `dict: {"system": ..., "user": ...}` | Nomes explicitos | Mais verboso; indices magicos |
| `tuple: (system, user)` | Conciso; encaixa padrao LangGraph | Requer ordem certa |

**Padrao LangGraph:** Messages sao `(role, content)` tuples. Nosso retorno `(system, user)` encaixa nativamente.

### Fluxo Completo: Exemplo Concreto

```python
# Entrada
result = render_generator_prompt(
    input_text="Scan https://shop.local for OWASP Top 10",
    backend_profile={
        "target": "https://shop.local",
        "framework": "Django",
        "auth": "JWT",
    },
    fase_index="## Available Phases\n- fase-1: Reconnaissance\n- fase-2: Auth Testing",
    execution_context="",
)

# Internamente
# 1. Load templates from src/pentest/templates/prompts/
# 2. Render generator_system.md.j2 (no variables) → system_str
# 3. Render generator_user.md.j2 with 4 variables → user_str
# 4. Return (system_str, user_str)

system, user = result

# Verificacao
assert "Generator agent" in system
assert "Maximum 15 subtasks" in system
assert "Scan https://shop.local" in user
assert "Django" in user
assert "fase-1: Reconnaissance" in user
```

---

## Testes (Layer 1 Unit Patterns)

**Localizacao:** `tests/unit/templates/test_renderer.py`

### Estrutura dos Testes

Os 11 testes unitarios verificam:

1. Que os templates sao **carregaveis e renderiziveis** sem erro
2. Que o output contem **palavras-chave arquiteturais criticas**
3. Que variaveis sao **injetadas corretamente**
4. Que condicionales funcionam (ex: `execution_context` vazio vs. preenchido)

### Testes Arquiteturais: Verificando Barreiras

```python
def test_system_prompt_mentions_available_tools(
    sample_backend_profile: dict, sample_fase_index: str
) -> None:
    """System prompt mentions available tools."""
    system_prompt, _ = render_generator_prompt(
        input_text="scan target",
        backend_profile=sample_backend_profile,
        fase_index=sample_fase_index,
    )

    assert "terminal" in system_prompt
    assert "browser" in system_prompt
    assert "searcher" in system_prompt
    assert "memorist" in system_prompt
```

**Proposito:** Sem invocar um LLM real, verificamos que a **invencao de ferramentas** e impossível. O prompt lista explicitamente as 4 permitidas.

```python
def test_system_prompt_specifies_subtask_requirements(
    sample_backend_profile: dict, sample_fase_index: str
) -> None:
    """System prompt specifies subtask structure requirements."""
    system_prompt, _ = render_generator_prompt(...)

    assert "title" in system_prompt
    assert "description" in system_prompt
    assert "fase" in system_prompt
    assert "15" in system_prompt  # 15-subtask limit
```

**Proposito:** Verificamos que a **barreira de 15 subtasks** e explícita. Se um LLM vê isto, propoe 15 ou menos.

### Testes de Variavel-Injecao

```python
def test_user_prompt_includes_input_text(
    sample_backend_profile: dict, sample_fase_index: str
) -> None:
    """User prompt includes the provided input text."""
    input_text = "scan https://example.com for vulnerabilities"

    _, user_prompt = render_generator_prompt(
        input_text=input_text,
        backend_profile=sample_backend_profile,
        fase_index=sample_fase_index,
    )

    assert input_text in user_prompt
```

**Proposito:** Renderer nao "come" dados. Tudo o que entra deve sair no prompt.

```python
def test_user_prompt_includes_execution_context_when_provided(
    sample_backend_profile: dict, sample_fase_index: str
) -> None:
    """User prompt includes execution context when provided."""
    context = "Previous findings: Port 443 has weak SSL cipher"

    _, user_prompt = render_generator_prompt(
        ...,
        execution_context=context,
    )

    assert context in user_prompt
    assert "Previous findings" in user_prompt
```

**Proposito:** Condicional `{% if execution_context %}` funciona. Contexto anterior e incluido.

### Teste de Condicional: execution_context Vazio

```python
def test_render_with_empty_execution_context(
    sample_backend_profile: dict, sample_fase_index: str
) -> None:
    """Rendering with empty execution_context parameter."""
    system_prompt, user_prompt = render_generator_prompt(
        input_text="scan https://target.local",
        backend_profile=sample_backend_profile,
        fase_index=sample_fase_index,
        execution_context="",
    )

    assert "first analysis phase" in user_prompt.lower()
```

**Proposito:** Condicional `{% else %}` renderiza. Primeira analise mostra mensagem apropriada.

### Matriz de Testes

| Teste | Input | Verificacao | Proposito |
|---|---|---|---|
| test_render_with_all_variables_populated | Todos os 4 parametros | Ambos prompts sao strings nao-vazias | Baseline: renderizacao basica funciona |
| test_system_prompt_contains_generator_role | generator_system.md.j2 | "Generator agent" e "SecureDev" presentes | Identidade do agente esta clara |
| test_system_prompt_mentions_available_tools | generator_system.md.j2 | "terminal", "browser", "searcher", "memorist" | Barreiras contra invencao de ferramentas |
| test_system_prompt_specifies_subtask_requirements | generator_system.md.j2 | "title", "description", "fase", "15" | 15-subtask limit e estrutura sao explicitas |
| test_user_prompt_includes_input_text | generator_user.md.j2 + `{{ input }}` | input_text e substring de user_prompt | Dados nao sao comidos pelo renderer |
| test_user_prompt_includes_backend_profile_json | generator_user.md.j2 + `{{ backend_profile }}` | Profile fields (ex: "Django") sao presentes | Backend context injetado corretamente |
| test_user_prompt_includes_fase_index | generator_user.md.j2 + `{{ fase_index }}` | fase_index e substring de user_prompt | Fases disponiveis listadas |
| test_user_prompt_includes_execution_context_when_provided | generator_user.md.j2 + condicional + contexto | execution_context e "Previous findings" presentes | Historico anterior incluido |
| test_render_with_empty_execution_context | generator_user.md.j2 + condicional + contexto="" | "first analysis phase" presente | Primeira analise vs. posterior diferenciadas |
| test_render_preserves_backend_profile_structure | Complex dict com arrays e nested objects | Todos os fields e sublistas presentes | Estruturas complexas preservadas |
| test_render_tuple_order_is_correct | Tuple return type | system primeiro, user segundo | LangGraph espera (system, user) |

### Cobertura Arquitetural

Os 11 testes cobrem:

- **Input Validation**: Variaveis sao aceites e renderizadas
- **Template Loading**: Ficheiros .j2 existem e sao processaveis
- **Jinja2 Processing**: Substituições de variaveis, condicionais, trim_blocks
- **Barrier Enforcement**: Limites (15 subtasks), inventario de ferramentas sao imutaveis
- **Role Definition**: Identidade do agente e clara
- **Output Structure**: Tuple order, string types

---

## Arquitetura de Integracao

### Fluxo no Contexto do Generator Agent

```
User Input: "scan https://example.com"
    ↓
FASE 0 Scanner
    ↓ (backend_profile JSON)
US-042 Skill Loader
    ↓ (fase_index string)
[render_generator_prompt] ← EU (US-043)
    ├─ Load templates
    ├─ Render system prompt (fixed instructions)
    ├─ Render user prompt (dynamic context)
    └─ Return (system_str, user_str)
    ↓
LangGraph/LangChain
    ├─ Pass system message to LLM
    ├─ Pass user message to LLM
    └─ Call LLM with tools (terminal, browser, searcher, memorist)
    ↓
Generator Agent (LLM)
    ├─ Reads system: "You are Generator. Max 15 subtasks. Tools: terminal, browser, searcher, memorist."
    ├─ Reads user: "Goal: scan target. Backend profile: Django, ports 80/443. Phases: fase-1, fase-3..."
    └─ Thinks and plans
    ↓
Tool Call: subtask_list
    └─ [
        {"title": "Port Scan", "description": "nmap target", "fase": "scan-fase-1"},
        {"title": "JWT Decode", "description": "Decode JWT tokens", "fase": "auth-fase-2"},
        ...
        ]
    ↓
Scanner Agent (US-044?)
    └─ Executa subtarefas
```

### Dependencias Entre USs

```
US-042 (Skill Loader)
    ↓ produce: fase_index
US-043 (Generator Prompts) ← EU
    ↓ consume: fase_index
    ├─ produce: system_prompt, user_prompt
    │
    └─ consumed by: Generator Agent (LangGraph)
        ↓
        Tool Calls (terminal, browser, searcher, memorist)
```

---

## Consideracoes de Design

### 1. Por que Tuple e Nao Dict?

**Opcao A (Dict):**
```python
return {
    "system": system_prompt,
    "user": user_prompt
}
```

**Opcao B (Tuple - Escolhida):**
```python
return (system_prompt, user_prompt)
```

**Justificacao:**
- LangGraph/LangChain usam frequentemente tuples para (role, content)
- Tuple e mais concisa (2 elementos)
- Ordem e implícita e documentada (system sempre primeiro)
- Acesso por indice [0] e [1] e padrao em Python

### 2. Por que Jinja2 e Nao Alternatives?

| Tool | Pros | Contras | Veredicto |
|---|---|---|---|
| **f-strings** | Simples, built-in | Sem condicionales; prompt espalhado no codigo | Rejeitado |
| **Template.format()** | Built-in | Sem condicionales | Rejeitado |
| **Jinja2** | Condicionales, loops, filtros; standard para templates | Dependencia externa | Aceito |
| **Mako** | Poderoso | Mais complexo, overkill | Rejeitado |

Jinja2 e a escolha standard em Python (Django templates, Flask, etc).

### 3. Environment Setup: trim_blocks vs. lstrip_blocks

```python
env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    trim_blocks=True,      # Remove linhas apos tags
    lstrip_blocks=True,    # Remove indentacao antes de tags
)
```

**Sem trim_blocks:**
```
Template:
{% if condition %}
Content
{% endif %}
More

Output:
(empty line)
Content
(empty line)
(empty line)
More
```

**Com trim_blocks e lstrip_blocks:**
```
Output:
Content
More
```

**Impacto:** Prompts sao mais limpos, sem whitespace excessivo.

---

## Ficheiros Criados

| Ficheiro | Tipo | Proposito |
|---|---|---|
| `src/pentest/templates/prompts/generator_system.md.j2` | Template Jinja2 | Instrucoes fixas e barreiras para o Generator |
| `src/pentest/templates/prompts/generator_user.md.j2` | Template Jinja2 | Contexto dinamico do target e da sessao |
| `src/pentest/templates/renderer.py` | Modulo Python | Funcao render_generator_prompt() |
| `tests/unit/templates/test_renderer.py` | Testes Unit | 11 testes Layer 1 |

---

## Resumo Executivo

**US-043** implementa a camada de **abstração de prompts** para o Generator agent. Em vez de construir prompts dinamicamente com string concatenation (fragil e dificil de auditar), usamos **templates Jinja2 versionaveis e condicionales**.

**Componentes:**

1. **generator_system.md.j2**: Define papel, ferramentas, limites (15 subtasks), estrutura de output
2. **generator_user.md.j2**: Assembla contexto dinamico (input, profile FASE 0, fases disponiveis, historico)
3. **renderer.py**: Carrega templates, renderiza com variaveis, retorna (system, user) tuple
4. **test_renderer.py**: 11 testes verificam renderizacao e presenca de palavras-chave arquiteturais

**Beneficios:**

- Prompts centralizados, nao espalhados em codigo
- Condicionales adaptam prompt ao estado (primeira analise vs. posterior)
- Barreiras imutaveis (tools, limits) vivem no prompt, nao em codigo
- Facil auditar historico de mudancas ao prompt via git
- Testes verificam integridade sem invocar LLM

**Pronto para**: Integracao com LangGraph para chamar o Generator agent com prompts confiavels.

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[USER-STORIES]]
- [[US-037-BASE-GRAPH-EXPLAINED]]
- [[US-042-SKILL-LOADER-EXPLAINED]]
