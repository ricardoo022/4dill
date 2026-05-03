---
tags: [agents]
---

# US-081: search_in_memory tool with flow/task/subtask filters — Explicacao Detalhada

Este documento explica a implementacao da tool `search_in_memory` para o agente Memorist, incluindo o modelo `SearchInMemoryAction` em `src/pentest/models/tool_args.py`, a factory function `create_search_in_memory_tool` em `src/pentest/tools/search_memory.py`, e os testes unitarios e de integracao correspondentes.

---

## Status: DONE (✅)

Esta User Story foi concluída. Todos os testes unitários, de integração e E2E estão a passar.

---

## Contexto

O agente Memorist precisa de pesquisar na memoria vetorial (pgvector) documentos relevantes para a tarefa atual, mas com filtros contextuais para limitar o scope da pesquisa. Sem filtros, uma pesquisa semantica devolve resultados de qualquer scan anterior, incluindo contextos irrelevantes. A `search_in_memory` resolve isto ao:

- Aceitar 1-5 queries semanticas para cobertura ampla do topic
- Suportar filtros opcionais por `task_id` e `subtask_id` para restringir ao contexto de execucao atual
- Fazer merge e deduplicacao de resultados multi-query
- Ordenar por score de relevancia (cosine distance convertido para score 0-1)
- Falhar gracefulmente quando o DB ou embeddings nao estao disponiveis

Esta tool complementa a `search_answer` (US-058) que ja existia: enquanto `search_answer` pesquisa documentos do tipo `answer` com filtro `answer_type`, a `search_in_memory` pesquisa **todos** os documentos do `VectorStore` com filtros contextuais de execucao (`task_id`, `subtask_id`), sem restricao de `doc_type`.

---

## `SearchInMemoryAction` (`src/pentest/models/tool_args.py`)

```python
class SearchInMemoryAction(BaseModel):
    """Schema for semantic search over vector memory with contextual filters."""

    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="1-5 semantic queries for searching vector memory",
    )
    task_id: int | None = Field(
        None,
        description="Optional task_id filter to constrain search scope",
    )
    subtask_id: int | None = Field(
        None,
        description="Optional subtask_id filter to constrain search scope",
    )
    max_results: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of results to return",
    )
    message: str = Field(
        ...,
        description="Human-facing explanation for this search",
    )

    @field_validator("queries")
    @classmethod
    def validate_queries_not_empty(cls, v: list[str]) -> list[str]:
        normalized = [q.strip() for q in v]
        if any(not q for q in normalized):
            raise ValueError("Each query must be non-empty.")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank or whitespace.")
        return v.strip()
```

| Campo | Tipo | Constraint/Default | Explicacao |
|-------|------|---------------------|------------|
| `queries` | `list[str]` | `min_length=1, max_length=5` | 1-5 queries semanticas para pesquisa |
| `task_id` | `int \| None` | `None` (opcional) | Filtra documentos por task_id no metadata |
| `subtask_id` | `int \| None` | `None` (opcional) | Filtra documentos por subtask_id no metadata |
| `max_results` | `int` | `10, ge=1, le=50` | Limite de resultados retornados |
| `message` | `str` | `...` (obrigatorio) | Descricao humana da pesquisa |

**Validador `validate_queries_not_empty`:**
1. Recebe a lista `v` de queries
2. Aplica `.strip()` a cada query para normalizar
3. Se alguma query ficar vazia apos strip, levanta `ValueError`
4. Retorna a lista normalizada

**Validador `validate_message_not_empty`:**
1. Recebe `v` (string)
2. Verifica se `v.strip()` e vazio
3. Se vazio, levanta `ValueError`
4. Retorna `v.strip()` para limpar espacos

**Porque e assim?**
- O limite de 5 queries evita chamadas excessivas ao provider de embeddings (custo e latencia)
- `task_id` e `subtask_id` sao opcionais porque nem todas as pesquisas precisam de contexto restrito — por vezes quer-se memoria global
- `max_results` default 10 equilibra riqueza de contexto com consumo de tokens no prompt do agente

---

## `create_search_in_memory_tool` (`src/pentest/tools/search_memory.py`)

```python
def create_search_in_memory_tool(db_session: AsyncSession | None) -> BaseTool:
    """
    Factory function to create the search_in_memory tool with an injected DB session.

    Performs multi-query semantic search over the vector store with optional
    contextual filters (task_id, subtask_id). Results are merged, deduplicated,
    and sorted by relevance score.
    """

    @tool(args_schema=SearchInMemoryAction)
    async def search_in_memory(
        queries: list[str],
        message: str = "",
        task_id: int | None = None,
        subtask_id: int | None = None,
        max_results: int = 10,
    ) -> str:
        """
        Search the vector memory for relevant documents using semantic similarity.
        Supports 1-5 queries with optional task_id and subtask_id filters.
        """
        del message

        if db_session is None:
            return "vector store not available"

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "embeddings not configured - set OPENAI_API_KEY"

        try:
            embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

            all_results: list[dict[str, Any]] = []
            seen_ids: set[int] = set()

            for query_text in queries:
                query_vector = await embeddings_model.aembed_query(query_text)

                # Build base similarity query
                stmt = (
                    select(
                        VectorStore,
                        VectorStore.embedding.cosine_distance(query_vector).label("distance"),
                    )
                    .where(VectorStore.embedding.cosine_distance(query_vector) <= 0.35)
                    .order_by(text("distance"))
                )

                # Apply optional metadata filters
                if task_id is not None:
                    stmt = stmt.where(
                        text("metadata_->>'task_id' = :tid").bindparams(tid=str(task_id))
                    )
                if subtask_id is not None:
                    stmt = stmt.where(
                        text("metadata_->>'subtask_id' = :sid").bindparams(sid=str(subtask_id))
                    )

                stmt = stmt.limit(max_results)

                result = await db_session.execute(stmt)
                for row, distance in result.all():
                    if row.id not in seen_ids:
                        seen_ids.add(row.id)
                        score = round(1.0 - float(distance), 2)
                        metadata = row.metadata_
                        all_results.append(
                            {
                                "content": row.content,
                                "score": score,
                                "doc_type": metadata.get("doc_type", "unknown"),
                                "flow_id": metadata.get("flow_id"),
                                "task_id": metadata.get("task_id"),
                                "subtask_id": metadata.get("subtask_id"),
                                "question": metadata.get("question"),
                                "answer_type": metadata.get("answer_type"),
                            }
                        )

            # Sort by score descending
            all_results.sort(key=lambda r: r["score"], reverse=True)

            # Apply overall max_results limit after merge
            all_results = all_results[:max_results]

            if not all_results:
                return "Nothing found in memory for these queries."

            # Format output
            lines = [f"Found {len(all_results)} relevant memory entries:"]
            for i, res in enumerate(all_results, start=1):
                score_fmt = f"{res['score']:.2f}"
                type_info = f" [{res['doc_type']}]"
                ctx_parts = []
                if res.get("flow_id"):
                    ctx_parts.append(f"flow={res['flow_id']}")
                if res.get("task_id"):
                    ctx_parts.append(f"task={res['task_id']}")
                if res.get("subtask_id"):
                    ctx_parts.append(f"subtask={res['subtask_id']}")
                ctx = f" ({', '.join(ctx_parts)})" if ctx_parts else ""

                lines.append(f"{i}. [Score: {score_fmt}]{type_info}{ctx}")
                content_lines = res["content"].strip().splitlines()
                if content_lines:
                    lines.append(f"   {content_lines[0]}")
                    for extra_line in content_lines[1:4]:
                        lines.append(f"      {extra_line}")
                    if len(content_lines) > 4:
                        lines.append("      ...")

            return "\n".join(lines)

        except Exception as exc:
            return f"search_in_memory tool error: {exc}"

    return search_in_memory
```

### Fluxo de execucao

```
START
  │
  ├─ db_session None? → "vector store not available" → END
  │
  ├─ OPENAI_API_KEY missing? → "embeddings not configured" → END
  │
  ├─ FOR each query in queries:
  │   ├─ Generate embedding via OpenAIEmbeddings.aembed_query()
  │   ├─ Build pgvector SELECT with cosine_distance <= 0.35
  │   ├─ Apply task_id filter (if provided) → metadata_->>'task_id' = :tid
  │   ├─ Apply subtask_id filter (if provided) → metadata_->>'subtask_id' = :sid
  │   ├─ Execute query, iterate results
  │   └─ Dedup by row.id → append to all_results with score = 1.0 - distance
  │
  ├─ Sort all_results by score DESC
  ├─ Apply max_results limit (slice)
  │
  ├─ Empty? → "Nothing found in memory" → END
  │
  └─ Format output → "Found N relevant memory entries:" + numbered list → END
```

### Decisoes de design

**Threshold 0.35 (cosine distance):**
A `search_answer` usa threshold 0.2 (mais restritiva, apenas answers confirmados). A `search_in_memory` usa 0.35 porque pesquisa **todos** os tipos de documento (vulnerabilities, findings, guides, code) — um threshold mais amplo permite encontrar documentos relevantes que estao ligeiramente mais distantes semanticamente mas ainda uteis para o contexto do agente.

**Deduplicacao por `row.id`:**
Quando multi-query retorna o mesmo documento para queries diferentes, o `seen_ids` set garante que cada documento aparece apenas uma vez no output. Isto evita ruido e poupa tokens no contexto do agente.

**Filtros como `text()` raw SQL:**
Os filtros `metadata_->>'task_id' = :tid` usam `text()` direto porque o SQLAlchemy 2.0 nao tem sintaxe nativa para operadores JSON do PostgreSQL (`->>`). O `bindparams()` garante que os valores sao parametrizados, prevenindo SQL injection.

**Output truncado a 4 linhas por entry:**
Cada resultado mostra a primeira linha do conteudo + ate 3 linhas extras. Se o conteudo tiver mais de 4 linhas, adiciona `"      ..."` para indicar truncacao. Isto controla o tamanho do output para nao consumir tokens excessivos no contexto do agente.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|----------|------------------|
| `src/pentest/models/tool_args.py` | Modelo `SearchInMemoryAction` com validacao |
| `src/pentest/tools/search_memory.py` | Factory function `create_search_in_memory_tool` |
| `tests/unit/tools/test_search_in_memory_unit.py` | 17 testes unitarios (schema, fallback, error handling, dedup) |
| `tests/integration/tools/test_search_in_memory_integration.py` | 7 testes de integracao (round-trip pgvector, filtros, merge) |
| `tests/e2e/tools/test_search_in_memory_e2e.py` | 3 testes e2e (embeddings reais + pgvector round-trip) |

---

## Testes E2E (`tests/e2e/tools/test_search_in_memory_e2e.py`)

Os testes E2E provam o ciclo completo com **embeddings reais da OpenAI** e **PostgreSQL+pgvector real**. Ao contrario dos testes de integracao que usam vetores mockados, estes geram embeddings reais via `OpenAIEmbeddings.aembed_query()` e verificam que a similaridade semantica funciona na pratica.

**Dependencias:** `OPENAI_API_KEY` definida, PostgreSQL acessivel em `TEST_DATABASE_URL`. Execucao manual apenas (`@pytest.mark.e2e`).

### `test_search_in_memory_real_embeddings_round_trip_e2e`

| Passo | Acao | Assert |
|-------|------|--------|
| 1 | Gera embeddings reais para 3 documentos (SQLi, XSS, SSH CVE) | Embeddings de 1536 dimensoes gerados |
| 2 | Insere no `vector_store` com metadata distinto | 3 rows na DB |
| 3 | Pesquisa com `"database injection bypass authentication"` (wording diferente do seed) | SQL injection aparece como top resultado |
| 4 | Verifica score > 0.5 | Embeddings reais produzem similaridade significativa |

**O que prova:** Os embeddings da OpenAI capturam semantica real — "database injection bypass authentication" encontra "SQL injection vulnerability in login endpoint" apesar da formulacao diferente.

### `test_search_in_memory_task_id_filter_real_embeddings_e2e`

| Passo | Acao | Assert |
|-------|------|--------|
| 1 | Gera embeddings reais para docs em task_id=1 e task_id=2 | 2 rows com task_ids diferentes |
| 2 | Pesquisa com filtro `task_id=1` | Apenas task_id=1 aparece |
| 3 | Verifica que task_id=2 nao aparece | Filtro funciona com embeddings reais |

### `test_search_in_memory_multi_query_merge_real_embeddings_e2e`

| Passo | Acao | Assert |
|-------|------|--------|
| 1 | Gera embeddings reais para 3 docs (SQLi, XSS, SSRF) | 3 rows distintas |
| 2 | Pesquisa com 2 queries que target docs diferentes | SQLi + XSS encontrados, SSRF nao aparece |
| 3 | Verifica ordenacao por score | SQL injection aparece antes de XSS (score mais alto) |

---

## Verificacao dos Acceptance Criteria

| Criterio | Status | Onde verificar |
|----------|--------|----------------|
| `search_in_memory` aceita 1-5 queries | ✓ | `SearchInMemoryAction.queries` com `min_length=1, max_length=5` |
| Suporta filtros por `task_id`/`subtask_id` | ✓ | Linhas 155-166 de `search_memory.py` (metadata filters) |
| Faz merge + deduplicacao de resultados multi-query | ✓ | `seen_ids` set + `all_results.sort()` em `search_memory.py` |
| Ordena por relevancia e aplica limite | ✓ | `all_results.sort(key=lambda r: r["score"], reverse=True)` + slice `[:max_results]` |
| Falha graceful quando DB/embeddings indisponiveis | ✓ | Checks de `db_session is None` e `OPENAI_API_KEY` |
| Prova em infra real com PostgreSQL+pgvector | ✓ | `tests/integration/tools/test_search_in_memory_integration.py` |
| Fallback explicito sem OPENAI_API_KEY | ✓ | `"embeddings not configured - set OPENAI_API_KEY"` |

---

## Verificacao dos Tests Required

| Teste | Status | Onde verificar |
|-------|--------|----------------|
| Multi-query com deduplicacao | ✓ | `test_search_in_memory_deduplication` (unit), `test_search_in_memory_multi_query_merge` (integration) |
| Sem resultados -> mensagem clara | ✓ | `test_search_in_memory_no_results` |
| Erros de DB/embedding -> tratamento robusto | ✓ | `test_search_in_memory_db_error_handling`, `test_search_in_memory_no_openai_key` |
| Com filtros e sem filtros | ✓ | `test_search_in_memory_task_id_filter`, `test_search_in_memory_subtask_id_filter` (unit + integration) |
| Integracao real com PostgreSQL+pgvector | ✓ | `test_search_in_memory_round_trip_real_pgvector` |
| Integracao real com filtro `task_id`/`subtask_id` | ✓ | `test_search_in_memory_task_id_filter`, `test_search_in_memory_subtask_id_filter` (integration) |
| E2E: embeddings reais + round-trip semantico | ✓ | `test_search_in_memory_real_embeddings_round_trip_e2e` |
| E2E: filtro task_id com embeddings reais | ✓ | `test_search_in_memory_task_id_filter_real_embeddings_e2e` |
| E2E: multi-query merge com embeddings reais | ✓ | `test_search_in_memory_multi_query_merge_real_embeddings_e2e` |

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[Epics/Memorist Agent/US-080-MEMORISTRESULT-MODEL-EXPLAINED]]
- [[Epics/Generator agent/US-037-BASE-GRAPH-EXPLAINED]]
- [[Epics/Searcher Agent/US-058-SEARCH-ANSWER-TOOL-EXPLAINED]]
