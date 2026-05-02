---
tags: [planning, scanner-agent, memory]
---

# Deep Dive: US-063 - Guide Tools (Search & Store)

Esta User Story implementa a memória de metodologias (Guides) para o **Scanner Agent**. Diferente do histórico de execução, os Guides são playbooks reutilizáveis que auxiliam o agente a executar ataques, bypasses e reconhecimentos complexos.

## Decisões de Arquitetura

1.  **Busca Semântica Multi-Query**: A ferramenta `search_guide` aceita até 5 questões simultâneas. O sistema realiza uma busca vetorial para cada questão e realiza o **Merge & Deduplicate**, mantendo apenas o resultado com maior score em caso de duplicidade.
2.  **Categorias Estritas (Enums)**: As ferramentas utilizam um Enum estrito para categorias, garantindo conformidade com os playbooks do sistema: `["install", "configure", "use", "pentest", "development", "other"]`.
3.  **Rastreabilidade (Metadados)**: A ferramenta `store_guide` captura metadados essenciais para orquestração, incluindo `flow_id`, `task_id`, `subtask_id`, e informações de particionamento (`part_size`, `total_size`).
4.  **Limiares e Filtros**:
    11:     *   **Threshold**: Apenas resultados com distância de cosseno <= 0.4 (Score >= 0.6) são considerados.
    12:     *   **Filtro**: A busca é restrita a documentos com `doc_type="guide"` e uma categoria específica (`guide_type`).

5.  **Anonimização Automática**: Antes de armazenar um guia via `store_guide`, o conteúdo passa por um processo de limpeza que mascara:
    *   Endereços IPv4.
    *   Credenciais em URLs (`http://user:pass@host`).
    *   Padrões comuns de atribuição de senhas, chaves e tokens (ex: `password: [REDACTED]`).
6.  **Disponibilidade**: A função `is_available()` permite verificar se a tool pode ser utilizada (ex: presença da `OPENAI_API_KEY`) antes da invocação.

## Modelos de Dados

### SearchGuideAction
*   `questions`: Lista de 1 a 5 strings.
*   `type`: Categoria do guia (Enum estrito).
*   `message`: Resumo da operação.

### StoreGuideAction
*   `guide`: Conteúdo em Markdown (mínimo 10 caracteres).
*   `question`: Questão principal que o guia responde.
*   `type`: Categoria do guia (Enum estrito).
*   `message`: Resumo da operação.
*   `flow_id`, `task_id`, `subtask_id`: Identificadores de rastreio (opcionais).
*   `part_size`, `total_size`: Metadados de particionamento (opcionais).

## Como executar os testes

Para validar as ferramentas de guia e a lógica de anonimização, execute:

```bash
pytest tests/unit/tools/test_guide.py -v
```

Para validar a tipagem e o linting:

```bash
mypy src/pentest/tools/guide.py
ruff check src/pentest/tools/guide.py
```
