---
tags: [agents, planning]
---

# US-064: Scanner prompt templates + FASE skill injection — Explicação Detalhada

Esta US implementa os templates de prompt do Scanner Agent, seguindo o padrão do PentAGI, mas adicionando a capacidade de injecção dinâmica de "fase skills" em runtime.

Ficheiros alterados:
- **`src/pentest/templates/scanner_system.md`**
- **`src/pentest/templates/scanner_user.md`**
- **`src/pentest/templates/__init__.py`**

## Contexto

O Scanner Agent é o principal executor técnico do sistema. Para que ele opere de forma eficiente e autónoma, necessita de um prompt de sistema rico que defina o seu papel, ferramentas disponíveis, contexto operacional (Docker) e regras de segurança (Barriers).

Diferente de outros agentes, o Scanner adapta o seu comportamento dependendo da **fase** do pentest em que se encontra (ex: Recon, Exploit, Post-Exploit). Isto é conseguido injectando o conteúdo de um ficheiro `SKILL.md` específico da fase directamente no system prompt.

## Implementação

### System Prompt Template (`src/pentest/templates/scanner_system.md`)

O template de sistema define a identidade do agente e o seu ambiente de trabalho.

```markdown
You are an Expert Pentester/Scanner Agent, part of the LusitAI autonomous penetration testing system. Your role is to execute technical subtasks within a controlled environment to identify and validate vulnerabilities.

## Operational Context
- **Docker Image:** {{ docker_image }}
- **Working Directory:** {{ cwd }}
{% if container_ports %}
- **Exposed Ports:** {{ container_ports | join(', ') }}
{% endif %}
- **Execution Context:** 
{{ execution_context }}

## Available Tools
The following tools are available to you:
{{ tool_names | join(', ') }}

## Rules of Engagement
- You are pre-authorized to perform all technical actions within the target scope.
- Efficiency is key: choose the most direct path to the subtask goal.
- You MUST verify your findings with evidence (command output, file content, etc.).
- Never perform actions outside the specified Docker environment.
- Use current time {{ current_time }} as reference for timestamped logs or time-sensitive checks.

## Phase Instructions (FASE)
{% if fase_skill %}
{{ fase_skill }}
{% else %}
Execute the subtask using your general pentesting expertise, following best practices for reconnaissance and exploitation.
{% endif %}

## Final Delivery
- You MUST use the `hack_result` tool to deliver your final findings.
- This is the barrier: once you call `hack_result`, your execution for this subtask terminates.
- Ensure the `result` field contains detailed technical evidence.
```

| Campo | Descrição |
|---|---|
| `docker_image` | Nome da imagem Docker onde o agente está a executar. |
| `cwd` | Directório de trabalho actual dentro do container. |
| `container_ports` | Lista de portos expostos no container. |
| `execution_context` | Contexto acumulado de passos anteriores (ex: resultados de scan de rede). |
| `tool_names` | Lista de nomes das ferramentas que o LLM pode invocar. |
| `fase_skill` | Conteúdo completo do ficheiro `SKILL.md` da fase actual. |
| `hack_result` | Tool de barreira obrigatória para entrega de resultados. |

### User Prompt Template (`src/pentest/templates/scanner_user.md`)

O template de utilizador é mantido curto e focado na tarefa imediata.

```markdown
Your Subtask:
{{ question }}
```

| Campo | Descrição |
|---|---|
| `question` | A tarefa ou pergunta específica delegada pelo Orchestrator. |

### Função de Renderização (`src/pentest/templates/__init__.py`)

A função `render_scanner_prompt` orquestra a carga dos templates e a injecção da fase.

```python
def render_scanner_prompt(
    question: str,
    execution_context: str,
    docker_image: str,
    cwd: str,
    container_ports: list[int],
    tool_names: list[str],
    current_time: str | None = None,
    fase: str | None = None,
    skills_dir: str | None = None,
) -> tuple[str, str]:
    # ... logic ...
    fase_skill = ""
    if fase and skills_dir:
        fase_skill = load_fase_skill(fase, skills_dir)
    
    # ... render templates ...
    return (system_prompt, user_prompt)
```

1.  **Carregamento da Skill:** Utiliza `load_fase_skill` para ir buscar o `SKILL.md` ao directório de skills (`lusitai-internal-scan`).
2.  **Ambiente Jinja2:** Configura o `FileSystemLoader` para apontar para o directório onde os ficheiros `.md` estão guardados.
3.  **Injecção:** O conteúdo da skill é passado para o template de sistema sob a variável `fase_skill`.

## Porquê esta Abordagem?

*   **Padrão PentAGI:** Mantemos a compatibilidade conceptual com o `pentester` original, facilitando a migração de lógica de prompts.
*   **Flexibilidade:** Ao injectar a `SKILL.md` no system prompt em vez de a passar como uma mensagem separada, garantimos que o LLM a trata como instruções fundamentais de comportamento e não apenas como dados de contexto.
*   **Transparência:** O uso de templates Markdown (.md) permite que os engenheiros de prompts editem as instruções sem tocar em código Python.

## Ficheiros Alterados

| Ficheiro | Descrição |
|---|---|
| `src/pentest/templates/scanner_system.md` | Template Jinja2 para o system prompt. |
| `src/pentest/templates/scanner_user.md` | Template Jinja2 para o user prompt. |
| `src/pentest/templates/__init__.py` | Exporta a função `render_scanner_prompt`. |

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Scanner Agent/Scanner Agent Hub]]
