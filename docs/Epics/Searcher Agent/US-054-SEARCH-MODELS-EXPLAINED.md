---
tags: [agents]
---

# US-054: Searcher Pydantic Models — Explicacao Detalhada

Este documento explica, em detalhe, a implementacao da `US-054` em `src/pentest/models/search.py` e os testes de validacao em `tests/unit/models/test_search_us054.py`.

---

## Objetivo da US

A `US-054` define os contratos de dados do Searcher para function calling:

1. `ComplexSearch` (delegacao entre agentes)
2. `SearchAction` (chamada a motores de pesquisa)
3. `SearchResult` (barrier/final result do Searcher)
4. `SearchAnswerAction` (pesquisa semantica no vector DB)

Todos com validacao forte e JSON schema compativel com LLM tool calling.

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/models/search.py` | Novos models Pydantic da US-054 |
| `src/pentest/models/tool_args.py` | Compatibilidade: re-export de `ComplexSearch` para call sites existentes |
| `src/pentest/tools/stubs.py` | Stub `searcher` atualizado para importar schema do novo modulo |
| `tests/unit/tools/test_stubs.py` | Testes de stubs atualizados para o novo import de `ComplexSearch` |
| `src/pentest/models/README.md` | Documentacao do modulo `search.py` e nota de re-export em `tool_args.py` |
| `tests/unit/models/test_search_us054.py` | Testes unitarios da story (valid/invalid/schema) |

---

## 1) `src/pentest/models/search.py` linha a linha

### Bloco de imports (linhas 1-3)

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator
```

| Linha | Explicacao |
|---|---|
| 1 | `Literal` limita valores permitidos de `type` em `SearchAnswerAction`. |
| 3 | `BaseModel` define schema/serializacao; `Field` adiciona constraints e metadata; `field_validator` valida e normaliza input. |

### `ComplexSearch` (linhas 6-17)

```python
class ComplexSearch(BaseModel):
    question: str = Field(..., description="Detailed query in English")
    message: str = Field(..., description="Short internal summary for downstream handoff")

    @field_validator("question", "message")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank or whitespace.")
        return v.strip()
```

| Linha(s) | Explicacao |
|---|---|
| 6 | Define o payload recebido pela tool de delegacao `search`. |
| 9-10 | Dois campos obrigatorios: pergunta detalhada + resumo curto interno para handoff/logs. |
| 12 | Um unico validator para ambos os campos, mantendo consistencia com `models/subtask.py`. |
| 15-16 | Rejeita string vazia ou so whitespace. |
| 17 | Normaliza input (trim), evitando ruido no estado do agente. |

### `SearchAction` (linhas 20-32)

```python
class SearchAction(BaseModel):
    query: str = Field(..., description="Short and precise search query")
    max_results: int = Field(5, ge=1, le=10, description="Maximum number of search results")
    message: str = Field(..., description="Description of what the search should find")
```

| Linha(s) | Explicacao |
|---|---|
| 20 | Define o contrato para tools de pesquisa (DuckDuckGo/Tavily). |
| 23 | `query` e obrigatoria e curta (sem default). |
| 24 | `max_results` tem default `5` e limites fortes `1..10` para evitar chamadas excessivas. |
| 25 | `message` documenta a intencao da pesquisa para rastreabilidade. |
| 27-32 | Mesmo padrao de validacao nao-vazio + trim para `query` e `message`. |

### `SearchResult` (linhas 35-46)

```python
class SearchResult(BaseModel):
    result: str = Field(..., description="Detailed search report in English")
    message: str = Field(..., description="Short internal summary for downstream handoff")
```

| Linha(s) | Explicacao |
|---|---|
| 35 | Contrato de saida final do Searcher (usado no barrier `search_result`, US-055). |
| 38 | `result`: resposta tecnica/detalhada para consumo do fluxo. |
| 39 | `message`: resumo curto para UX. |
| 41-46 | Rejeita vazio/whitespace e normaliza com trim para consistencia no output. |

### `SearchAnswerAction` (linhas 49-77)

```python
class SearchAnswerAction(BaseModel):
    questions: list[str] = Field(..., min_length=1, max_length=5, ...)
    type: Literal["guide", "vulnerability", "code", "tool", "other"] = Field(...)
    message: str = Field(...)
```

| Linha(s) | Explicacao |
|---|---|
| 49 | Contrato para pesquisa semantica no vector DB (`search_answer`, US-058). |
| 52-57 | `questions` exige lista entre 1 e 5 elementos. |
| 58-61 | `type` e fechado por `Literal` para filtro consistente no backend. |
| 62 | `message` obrigatoria para contexto humano/logging. |
| 64-70 | Validator de lista: aplica `strip()` a cada item e falha se algum ficar vazio. |
| 72-77 | Validator de `message` com o mesmo padrao de nao-vazio + trim. |

---

## 2) Como o schema fica compativel com function calling

Como todos os modelos herdam de `BaseModel` e usam `Field(...)`/constraints:

1. `model_json_schema()` expoe `properties` para cada argumento da tool.
2. Campos sem default aparecem em `required`.
3. Limites (`ge`, `le`, `min_length`, `max_length`) ficam no schema para orientar o LLM e validar runtime.
4. `Literal[...]` vira enum no schema JSON.

Isto e exatamente o que as tools LangChain esperam em `args_schema`.

---

## 3) Testes da US-054 (`tests/unit/models/test_search_us054.py`)

### Cobertura por requisito

| Requisito da US | Teste |
|---|---|
| `ComplexSearch` valido | `test_complex_search_valid_pentest_query` |
| `ComplexSearch` invalido (question vazio) | `test_complex_search_rejects_empty_question` |
| `SearchAction` valido | `test_search_action_valid_query_defaults_and_bounds` |
| `SearchAction` invalido (`max_results=0`) | `test_search_action_rejects_max_results_below_min` |
| `SearchAction` invalido (`max_results=11`) | `test_search_action_rejects_max_results_above_max` |
| `SearchResult` valido | `test_search_result_valid_report_and_message` |
| `SearchAnswerAction` valido | `test_search_answer_action_valid_single_question` |
| `SearchAnswerAction` invalido (lista vazia) | `test_search_answer_action_rejects_empty_questions_list` |
| `SearchAnswerAction` invalido (>5 items) | `test_search_answer_action_rejects_too_many_questions` |
| `SearchAnswerAction` invalido (type fora do enum) | `test_search_answer_action_rejects_invalid_type` |
| JSON schema com `properties` e `required` | `test_all_search_models_json_schema_function_calling_shape` |

### Nota de implementacao

O ultimo teste usa `pytest.mark.parametrize` para validar os 4 modelos com a mesma regra de schema, reduzindo duplicacao sem perder clareza.

---

## 4) Decisoes de design importantes

1. **Validacao central por model**: cada model protege o seu proprio boundary (nao delega para chamadas externas).
2. **Normalizacao por trim**: evita persistir/propagar strings com ruido.
3. **Limites numericos/lista no schema**: protege custo/performance e impede payloads absurdos.
4. **Enum fechado em `type`**: simplifica filtros e evita estados invalidos no Searcher pipeline.

---

## 5) Resultado pratico da US-054

Depois desta US, o projeto passou a ter contratos estaveis para o Searcher que desbloqueiam:

- US-055 (`SearchResult` no barrier `search_result`)
- US-056/US-057 (`SearchAction` para motores de pesquisa)
- US-058 (`SearchAnswerAction` para pesquisa no vector DB)
- US-060 (`ComplexSearch` na delegacao para o Searcher)

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]]
- [[US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED]]
- [[US-057-TAVILY-SEARCH-TOOL-EXPLAINED]]
