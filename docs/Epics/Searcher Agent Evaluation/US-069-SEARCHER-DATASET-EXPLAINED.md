---
tags: []
---

# US-069: Searcher Dataset — Explicacao Detalhada

Os seguintes ficheiros foram criados para fornecer o ground truth e avaliação do agente Searcher:
- `tests/evals/searcher/datasets/searcher.json`
- `tests/evals/searcher/datasets/README.md`
- `tests/evals/searcher/test_dataset.py`

## Contexto

O objetivo desta User Story é criar um dataset curado de avaliação (ground truth) para o agente Searcher. Ao contrário do Generator que depende de ambientes com vulnerabilidades, o Searcher precisa de factos garantidos, restrições comportamentais, e fontes verificáveis. Este dataset reflete casos de uso reais num processo de pentesting (como pesquisa de vulnerabilidades, bypasses, instruções em memórias internas e exploração web).

## Ficheiros Alterados

| Ficheiro | Propósito |
|---|---|
| `tests/evals/searcher/datasets/searcher.json` | Dataset com os 12 cenários de ground truth. |
| `tests/evals/searcher/datasets/README.md` | Documentação com a schema do dataset e processos de adição/validação. |
| `tests/evals/searcher/test_dataset.py` | Testes automatizados (pytest) para garantir a integridade do JSON e as quotas de cenários (`memory` e `browser_followup`). |

---

## Dataset de Avaliação (searcher.json)

O ficheiro contém 12 cenários estruturados segundo uma schema rigorosa:

```json
{
  "inputs": {
    "question": "What is the internal guideline for handling SQL injection in legacy applications?",
    "context": "Context: Working on an old PHP application"
  },
  "reference_outputs": {
    "required_facts": [
      "Must use prepared statements",
      "Legacy code must be wrapped in protective layer"
    ],
    "acceptable_sources": [
      "internal-wiki.local"
    ],
    "expected_tools": [
      "search_answer"
    ],
    "disallowed_behaviors": [
      "Inventing internal policies",
      "Suggesting outside internet sources"
    ]
  },
  "metadata": {
    "category": "memory",
    "difficulty": "easy"
  }
}
```

**Esquema de Campos:**
| Campo | Tipo | Explicação |
|---|---|---|
| `inputs.question` | `string` | A query feita pelo utilizador/avaliador. |
| `inputs.context` | `string` | O contexto em que a query é realizada. |
| `reference_outputs.required_facts` | `list[string]` | Frases curtas e verificáveis que o agente deve mencionar na resposta. |
| `reference_outputs.acceptable_sources` | `list[string]` | Domínios ou prefixos de URL válidos de onde extrair a informação. |
| `reference_outputs.expected_tools` | `list[string]` | As ferramentas esperadas durante a trajectory de execução. |
| `reference_outputs.disallowed_behaviors` | `list[string]` | Ações estritamente proibidas no output do agente (ex.: alucinações). |
| `metadata.category` | `string` | Tipo de cenário (`cve`, `version`, `technique`, `tool`, `memory`, `browser_followup`). |
| `metadata.difficulty` | `string` | Complexidade da tarefa de avaliação (`easy`, `medium`, `hard`). |

---

## Testes de Integridade (test_dataset.py)

A suíte de testes em Pytest assegura as propriedades estabelecidas nos Acceptance Criteria:

```python
def test_searcher_dataset_valid() -> None:
    dataset_path = Path("tests/evals/searcher/datasets/searcher.json")
    assert dataset_path.exists(), "Dataset file should exist"
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
...
    # Specific quota constraints
    assert memory_count >= 3, "Must have at least 3 'memory' scenarios"
    assert browser_count >= 3, "Must have at least 3 'browser_followup' scenarios"
```

A função garante:
1. Parse válido do JSON.
2. Presença e validade dos campos críticos para todos os 12 cenários.
3. Não existem questões (`inputs.question`) duplicadas.
4. Cumprimento do requisito restrito (pelo menos 3 `memory` com `search_answer` e pelo menos 3 `browser_followup` com `browser`).

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
