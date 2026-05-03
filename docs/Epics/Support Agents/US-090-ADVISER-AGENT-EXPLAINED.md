---
tags: [agents]
---

# US-090: Adviser Agent — Explicacao Detalhada

Este documento detalha a implementacao do Adviser Agent, um agente de suporte estrategico que funciona como uma cadeia LLM simples para fornecer orientacao aos outros agentes do sistema.

## Contexto

O Adviser e o primeiro "Support Agent" do LusitAI. Ele resolve o problema de agentes ficarem "presos" em loops ineficientes ou nao saberem como prosseguir apos uma barreira tecnica. 
Suas principais responsabilidades sao:
- Analisar o contexto atual e os findings de um scan.
- Fornecer recomendacoes estrategicas acionaveis.
- Sugerir bypasses, tecnicas ou ferramentas especificas.
- Manter uma visao de alto nivel do objetivo do pentest.

Diferente dos agentes principais (como o Generator ou o Scanner), o Adviser nao usa um loop de LangGraph nem executa ferramentas proprias. Ele e uma "pure model call" que recebe input e devolve texto.

---

## `AdviserInput` (`src/pentest/models/tool_args.py`)

O modelo Pydantic que define os argumentos aceitos pela tool `advice`.

```python
class AdviserInput(BaseModel):
    """Schema for requesting strategic guidance from the Adviser agent."""

    question: str = Field(..., min_length=1, description="The strategic question or problem")
    context: str = Field(..., min_length=1, description="Current findings or specific problem context")
    execution_context: str = Field(
        "", description="Optional historical context from previous steps"
    )
```

| Campo | Tipo | Descricao |
|---|---|---|
| `question` | `str` | A pergunta estrategica ou o problema tecnico que precisa de resolucao. |
| `context` | `str` | Findings atuais, outputs de tools ou o estado especifico onde o agente esta preso. |
| `execution_context` | `str` | (Opcional) Historico de execucao ou passos anteriores para dar contexto temporal. |

---

## Templates Jinja2 (`src/pentest/templates/prompts/`)

O Adviser utiliza dois templates para construir o prompt final.

### `adviser_system.md.j2`

Define o papel, autorizacao e regras de comportamento do agente.

```markdown
# Role: Strategic Cybersecurity Consultant (Adviser Agent)

You are the Adviser, an expert strategic cybersecurity consultant and penetration testing lead. Your role is to provide high-level guidance, strategic advice, and creative solutions to other agents when they are stuck, encountering unexpected barriers, or need to prioritize their next moves.

... (regras de eficiencia e seguranca)
```

### `adviser_user.md.j2`

Estrutura o pedido de assistencia com as variaveis passadas.

```markdown
# Strategic Assistance Request

I am currently performing a penetration test and I need your guidance on a specific problem.

## The Question
{{ question }}

## Current Context & Findings
{{ context }}

{% if execution_context %}
## Execution History / Previous Steps
{{ execution_context }}
{% endif %}

Please analyze the situation and provide your strategic recommendation.
```

---

## `render_adviser_prompt` (`src/pentest/templates/adviser.py`)

Funcao responsavel por renderizar os templates usando o motor Jinja2 do projeto.

```python
def render_adviser_prompt(
    question: str, context: str, execution_context: str = ""
) -> tuple[str, str]:
    system_prompt = render_template("adviser_system.md.j2", {})
    user_prompt = render_template(
        "adviser_user.md.j2",
        {
            "question": question,
            "context": context,
            "execution_context": execution_context,
        },
    )
    return system_prompt, user_prompt
```

| Passo | Accao |
|---|---|
| 1 | Renderiza o template de sistema (estatico). |
| 2 | Renderiza o template de utilizador injetando a questao e os contextos. |
| 3 | Retorna o par de prompts prontos para consumo pelo LLM. |

---

## `give_advice` (`src/pentest/agents/adviser.py`)

O core do agente Adviser. Implementa uma cadeia simples assincrona.

```python
async def give_advice(
    question: str,
    context: str,
    llm: BaseChatModel | None = None,
    execution_context: str = "",
) -> str:
    if llm is None:
        llm = _resolve_adviser_llm()

    system_prompt, user_prompt = render_adviser_prompt(
        question=question,
        context=context,
        execution_context=execution_context,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    return str(response.content)
```

### Porque e assim?
O Adviser nao precisa de um grafo LangGraph porque sua tarefa e puramente analitica e unidirecional. Ele nao precisa decidir "qual ferramenta usar", ele apenas responde a uma pergunta. Isso economiza tokens e latencia.

---

## `create_advice_tool` (`src/pentest/tools/adviser.py`)

Factory que cria a tool `advice` para ser usada por outros agentes.

```python
def create_advice_tool(llm: BaseChatModel) -> BaseTool:
    async def advice_handler(question: str, context: str, execution_context: str = "") -> str:
        try:
            return await give_advice(
                question=question,
                context=context,
                llm=llm,
                execution_context=execution_context,
            )
        except Exception as e:
            return f"advice tool error: {e}"

    return StructuredTool.from_function(
        name="advice",
        coroutine=advice_handler,
        description="Request strategic guidance or advice from a senior consultant when stuck or needing direction. Provide a clear question, current context, and optionally the execution history.",
        args_schema=AdviserInput,
    )
```

| Elemento | Configuracao |
|---|---|
| Nome | `advice` |
| Args Schema | `AdviserInput` (validacao Pydantic automatica) |
| Async | Sim (usando `coroutine`) |
| Erros | Capturados e retornados como string (padrao do projeto) |

---

## Exemplo Completo

**Cenario:** O Scanner esta preso num filtro de WAF ao tentar fazer brute force de diretorios.

**Input via Tool:**
```json
{
  "question": "How can I bypass the WAF blocking my directory fuzzing attempts on /api/v1?",
  "context": "nmap found port 443 open. ffuf results show 403 Forbidden for all common paths after 10 requests. Target seems to be using Cloudflare.",
  "execution_context": "Tried changing User-Agent and adding X-Forwarded-For headers, still blocked."
}
```

**Fluxo Interno:**
1. O agente (ex: Scanner) chama a tool `advice`.
2. A tool invoca `give_advice`.
3. `render_adviser_prompt` gera os prompts.
4. O LLM (ex: Claude 3.5 Sonnet) analisa e responde.

**Output (Conselho):**
> "The WAF is likely rate-limiting your requests based on IP and header patterns. Instead of aggressive fuzzing, I recommend:
> 1. Try slow-scanning with `--rate 1` or a larger delay.
> 2. Use `curl` to test for 'Cloudflare-Skip-WAF' or other misconfigured bypass headers if the origin IP can be found.
> 3. Focus on subdomains (e.g., dev.target.com) which might have weaker WAF rules.
> 4. Try techniques like 'Unicode normalization' or 'Path obfuscation' (e.g., /api/./v1/)."

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/models/tool_args.py` | Definicao do esquema de input `AdviserInput`. |
| `src/pentest/templates/prompts/adviser_system.md.j2` | Template de sistema do Adviser. |
| `src/pentest/templates/prompts/adviser_user.md.j2` | Template de utilizador do Adviser. |
| `src/pentest/templates/adviser.py` | Logica de renderizacao de prompts. |
| `src/pentest/agents/adviser.py` | Implementacao da cadeia LLM e logica do agente. |
| `src/pentest/tools/adviser.py` | Factory da tool de delegacao para o Adviser. |

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[US-037-AGENT-STATE-BASE-GRAPH-EXPLAINED]]
