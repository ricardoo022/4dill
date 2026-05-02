# tests/unit/templates/

Testes unitários de `templates/renderer.py` — renderização de prompts Jinja2.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `__init__.py` | Package init |
| `test_renderer.py` | Testa `render_generator_prompt()` com variáveis de contexto reais e edge cases |
| `test_searcher_templates.py` | Testa `render_searcher_prompt()` para verificar conformidade com US-059: prioridade de fontes, protocolo, anonimizacao (US-059) |

## O que é testado

- `render_generator_prompt(scan_path, skills_index)` produz string não-vazia com as variáveis interpoladas
- Templates `generator_system.md.j2` e `generator_user.md.j2` são encontrados e carregados
- Variáveis `scan_path` e `skills_index` substituídas correctamente no output
- `scan_path` vazio ou `skills_index` vazio não crasham o renderer
- `render_searcher_prompt(question, available_tools, task, subtask, execution_context)` produz prompts não-vazios (US-059)
- Searcher system prompt contém prioridade de fontes (search_answer primeiro)
- Searcher system prompt contém instruções sobre `search_result` barrier
- Searcher system prompt NÃO contém referências a `store_answer` (proibido por US)
- Searcher user message renderiza com campos opcionais vazios ou preenchidos sem erro

## Módulo de produção

- `src/pentest/templates/renderer.py` — ver `docs/Epics/Generator agent/US-043-GENERATOR-PROMPTS-EXPLAINED.md`
- `src/pentest/templates/searcher.py` — ver `docs/Epics/Searcher Agent/US-059-Searcher-prompt-templates-EXPLAINED.md`
