---
tags: [agents, database]
---

# US-058: search_answer tool (pgvector read) — Explicacao Detalhada

Este documento explica a implementacao da US-058 em `src/pentest/tools/search_memory.py` e `src/pentest/models/search.py` (campo `SearchAnswerAction`), com cobertura dos testes em `tests/unit/tools/test_search_memory_unit.py` e `tests/integration/tools/test_search_memory_integration.py`.

---

## Contexto

O Searcher tem duas fontes de informacao: a web (DuckDuckGo, Tavily) e o **vector store** — uma base de dados de respostas de scans anteriores. A `search_answer` tool e a ponte para essa segunda fonte.

- Cada vez que o Reporter termina um scan, guarda Q&A pairs no `vector_store` (tabela PostgreSQL com coluna `embedding vector(1536)`).
- Em scans seguintes, antes de ir para a web, o Searcher **primeiro consulta este store** — se a resposta ja existe, poupa tempo e tokens.
- A pesquisa e semantica: usa embeddings (`text-embedding-3-small`) para encontrar respostas com significado similar, nao apenas coincidencia de palavras.
- A tool suporta multiplas queries em paralelo (1-5) e deduplica resultados para evitar repeticoes.
- E uma **factory function** porque precisa de uma `AsyncSession` do SQLAlchemy injectada em runtime (dependency injection via closure). Sem sessao, retorna tool degradada gracefully.
- Filtra por `doc_type="answer"` e por `answer_type` (guide, vulnerability, code, tool, other) para que o Searcher receba apenas o tipo de resposta que pediu.

---

## Referencia PentAGI (Go)

### `SearchAnswerToolName` (`pentagi/backend/pkg/tools/search.go`, linhas 67-197)

```go
case SearchAnswerToolName:
    var action SearchAnswerAction
    if err := json.Unmarshal(args, &action); err != nil {
        return "", fmt.Errorf("failed to unmarshal %s search answer action arguments: %w", name, err)
    }

    filters := map[string]any{
        "doc_type":    searchVectorStoreDefaultType,
        "answer_type": action.Type,
    }

    // Execute multiple queries and collect all documents
    var allDocs []schema.Document
    for i, query := range action.Questions {
        docs, err := s.store.SimilaritySearch(
            ctx,
            query,
            searchVectorStoreResultLimit,  // 3
            vectorstores.WithScoreThreshold(searchVectorStoreThreshold),  // 0.8 (similarity)
            vectorstores.WithFilters(filters),
        )
        // ...
        allDocs = append(allDocs, docs...)
    }

    // Merge, deduplicate, sort by score, and limit results
    docs := MergeAndDeduplicateDocs(allDocs, searchVectorStoreResultLimit)

    if len(docs) == 0 {
        return searchNotFoundMessage, nil
    }

    buffer := strings.Builder{}
    for i, doc := range docs {
        buffer.WriteString(fmt.Sprintf("# Document %d Search Score: %f\n\n", i+1, doc.Score))
        buffer.WriteString(fmt.Sprintf("## Original Answer Type: %s\n\n", doc.Metadata["answer_type"]))
        buffer.WriteString(fmt.Sprintf("## Original Search Question\n\n%s\n\n", doc.Metadata["question"]))
        buffer.WriteString("## Content\n\n")
        buffer.WriteString(doc.PageContent)
        buffer.WriteString("\n\n")
    }
    return buffer.String(), nil
```

**Diferencas chave face ao Python:**

| Aspeto | Go (PentAGI) | Python (LusitAI) |
|---|---|---|
| Threshold | `0.8` similarity (score >= 0.8) | `0.2` cosine distance (<= 0.2) — equivalente matematico |
| Vector store | `langchain-go` `vectorstores.VectorStore` interface | SQLAlchemy directo com `pgvector` extension |
| Deduplicacao | `MergeAndDeduplicateDocs()` funcao separada | `seen_ids: set[int]` inline na closure |
| Output format | Markdown com `# Document N`, `## Original Answer Type`, `## Content` | Formato compacto: `[Score: X.XX] Q: "..." \n A: ...` |
| Observability | Langfuse tracing integrado | Sem tracing na v1 |
| Sessao DB | `s.store` (injectado no struct) | `db_session` capturado em closure |

O Go usa a abstraction `vectorstores.VectorStore` do LangChain Go, que esconde os detalhes da query pgvector. O Python acede directamente ao SQLAlchemy + pgvector extension — mais verboso, mas sem dependencias adicionais.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/models/search.py` | Define `SearchAnswerAction` — args schema da tool (campos + validacao) |
| `src/pentest/tools/search_memory.py` | `create_search_answer_tool()` — factory + closure `search_answer` |
| `tests/unit/tools/test_search_memory_unit.py` | 6 testes unitarios com mocks (sem DB real) |
| `tests/integration/tools/test_search_memory_integration.py` | 1 teste de integracao com pgvector real |

---

## `SearchAnswerAction` (`src/pentest/models/search.py`, linhas 49-77)

`SearchAnswerAction` e o schema Pydantic que o LangChain usa para validar os argumentos quando o LLM invoca a tool via function calling. Se o LLM enviar dados invalidos, Pydantic rejeita antes de o codigo de pesquisa sequer executar.

```python
class SearchAnswerAction(BaseModel):
    """Schema for vector database search requests."""

    questions: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Semantic queries for searching previous answers",
    )
    type: Literal["guide", "vulnerability", "code", "tool", "other"] = Field(
        ...,
        description="Answer type filter",
    )
    message: str = Field(..., description="User-facing explanation for this action")

    @field_validator("questions")
    @classmethod
    def validate_questions_not_empty(cls, v: list[str]) -> list[str]:
        normalized = [question.strip() for question in v]
        if any(not question for question in normalized):
            raise ValueError("Each question must be non-empty.")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank or whitespace.")
        return v.strip()
```

### Campos

| Campo | Tipo | Obrigatorio | Restricoes | Descricao |
|---|---|---|---|---|
| `questions` | `list[str]` | sim | min 1 item, max 5 items | Lista de queries semanticas para pesquisar no vector store. Cada query deve ser nao-vazia apos strip. |
| `type` | `Literal[...]` | sim | `"guide"`, `"vulnerability"`, `"code"`, `"tool"`, `"other"` | Filtro de tipo — so retorna respostas com `answer_type` correspondente. |
| `message` | `str` | sim | nao pode ser blank | Explicacao legivel do que o agente esta a procurar. Usado para logs/audit, nao afecta a query. |

### Validators

#### `validate_questions_not_empty` (linhas 64-69)

```python
@field_validator("questions")
@classmethod
def validate_questions_not_empty(cls, v: list[str]) -> list[str]:
    normalized = [question.strip() for question in v]
    if any(not question for question in normalized):
        raise ValueError("Each question must be non-empty.")
    return normalized
```

**Regra:** Cada string dentro de `questions` deve ter pelo menos um caracter nao-whitespace.

**Porque e assim?** O LLM pode enviar `["CVE nginx", "", "bypass WAF"]` — a segunda query e vazia. Uma query vazia geraria um embedding de string vazia, que produziria um vector de baixa qualidade e possivelmente retornaria resultados aleatorios do store. O validator apanha isto antes que o custo do embedding API call seja incorrido.

**Side effect util:** `normalized` retorna as questions ja com `.strip()` aplicado — `"  nginx vuln  "` passa a `"nginx vuln"`. Este strip reduz variacao semantica desnecessaria no embedding.

#### `validate_message_not_empty` (linhas 72-76)

```python
@field_validator("message")
@classmethod
def validate_message_not_empty(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("Field cannot be blank or whitespace.")
    return v.strip()
```

**Regra:** O campo `message` nao pode ser vazio ou so whitespace.

**Porque e assim?** O `message` e um contrato de auditabilidade — o agente deve sempre justificar porque esta a pesquisar no vector store. Uma `message` vazia seria como um comentario vazio: nao tem valor para logs nem para debugging posterior de comportamento inesperado do agent.

### Por que `type` usa `Literal` e nao `StrEnum`?

O `Literal["guide", "vulnerability", "code", "tool", "other"]` define o schema JSON com valores exactos. O LLM ve estes valores no function schema e **escolhe o correcto** sem improviso. Se fosse `str` livre, o LLM poderia enviar `"vuln"` ou `"Vulnerability"` — que nao matchariam o filtro JSONB `answer_type = :atype` na query SQL.

---

## `create_search_answer_tool` (`src/pentest/tools/search_memory.py`)

### Estrutura da factory e closure

```python
def create_search_answer_tool(db_session: AsyncSession | None) -> BaseTool:
    @tool(args_schema=SearchAnswerAction)
    async def search_answer(
        questions: list[str],
        type: str,  # noqa: A002
        message: str = "",
    ) -> str:
        """
        Search previous scan answers in the vector store before going to the web.
        Use this to find confirmed vulnerabilities, guides, or code snippets from earlier scans.
        """
        del message

        if db_session is None:
            return "vector store not available"
        # ...

    return search_answer
```

**Cadeia de closure:**

```
create_search_answer_tool(db_session)   ← outer function
    │
    │  captura: db_session
    │
    └─► search_answer(questions, type, message)   ← inner tool
            │
            └─► acede: db_session  (via closure, nao parametro)
```

| Elemento | Explicacao |
|---|---|
| `db_session: AsyncSession \| None` | Parametro da factory. Se `None`, a tool retorna "not available" sem crash. |
| `@tool(args_schema=SearchAnswerAction)` | Decorador LangChain — transforma `search_answer` num `BaseTool`. O `args_schema` vincula o schema Pydantic para validacao e function calling. |
| `# noqa: A002` | Suprime aviso de ruff sobre shadowing do built-in `type`. Necessario porque o schema usa este nome para consistencia com o LLM. |
| `del message` | Descarta o campo de auditabilidade — ja foi validado pelo Pydantic, mas nao e usado na query. |
| `return search_answer` | Retorna o `BaseTool` construido — pronto a ser passado a `create_agent_graph(tools=[...])`. |

**Porque factory e nao funcao simples?** O `db_session` e criado no lifecycle do controller (uma sessao por request/scan). Uma funcao simples `@tool` nao pode receber `db_session` como argumento porque o LangChain injeta apenas os argumentos definidos no `args_schema`. A factory captura a sessao via closure, mantendo o schema do LLM limpo.

---

### Verificacoes iniciais (`search_answer`, linhas 41-50)

```python
if db_session is None:
    return "vector store not available"

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    return "embeddings not configured - set OPENAI_API_KEY"

embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
```

| Linha(s) | Explicacao |
|---|---|
| `if db_session is None:` | Guard redundante (a factory ja verifica), mas protege contra uso directo da closure. |
| `os.getenv("OPENAI_API_KEY")` | Lido em runtime (nao na factory) — permite mudar a key sem reiniciar o processo. |
| `return "embeddings not configured..."` | Graceful degradation: o agente ve esta mensagem e pode decidir ir directamente para a web. Nao e um crash. |
| `OpenAIEmbeddings(model="text-embedding-3-small")` | 1536 dimensoes. Mesmo modelo que o Reporter usa para guardar as respostas — dimensoes incompativeis causariam resultados errados. |

---

### Loop de pesquisa e query pgvector (linhas 52-86)

```python
all_results: list[dict[str, Any]] = []
seen_ids: set[int] = set()

for question in questions:
    query_vector = await embeddings_model.aembed_query(question)

    stmt = (
        select(
            VectorStore,
            VectorStore.embedding.cosine_distance(query_vector).label("distance"),
        )
        .where(text("metadata_->>'doc_type' = 'answer'"))
        .where(text("metadata_->>'answer_type' = :atype").bindparams(atype=type))
        .where(VectorStore.embedding.cosine_distance(query_vector) <= 0.2)
        .order_by(text("distance"))
        .limit(3)
    )

    result = await db_session.execute(stmt)
    for row, distance in result.all():
        if row.id not in seen_ids:
            seen_ids.add(row.id)
            score = 1.0 - float(distance)
            all_results.append({
                "question": row.metadata_.get("question", "Unknown"),
                "answer": row.content,
                "score": score,
            })
```

#### Anatomia da query SQLAlchemy

| Clausula | Explicacao |
|---|---|
| `select(VectorStore, VectorStore.embedding.cosine_distance(query_vector).label("distance"))` | Selecciona a row completa + o valor de distancia coseno calculado pelo pgvector. O `.label("distance")` permite referenciar este valor calculado noutras clausulas. |
| `.where(text("metadata_->>'doc_type' = 'answer'"))` | Filtro JSONB via operador PostgreSQL `->>` (extrai valor como text). So retorna documentos marcados como respostas (nao outros tipos como "context" ou "code"). |
| `.where(text("metadata_->>'answer_type' = :atype").bindparams(atype=type))` | Filtro parametrizado por tipo. `.bindparams()` e seguro contra SQL injection — o valor e passado como parametro, nao interpolado. |
| `.where(VectorStore.embedding.cosine_distance(query_vector) <= 0.2)` | **Threshold de similaridade.** Cosine distance de 0.0 = identico, 1.0 = completamente diferente. `<= 0.2` equivale a `>= 0.8` de similaridade coseno — so retorna respostas bastante proximas semanticamente. |
| `.order_by(text("distance"))` | Ordena pelo valor calculado mais proximo primeiro. O agente ve primeiro a resposta mais relevante. |
| `.limit(3)` | Max 3 resultados por query. Com 5 queries possiveis, o maximo teorico e 15 resultados (antes de deduplicacao). |

#### Deduplicacao

```python
if row.id not in seen_ids:
    seen_ids.add(row.id)
```

Quando multiplas queries produzem o mesmo documento (ex: "nginx bypass" e "nginx WAF evasion" retornam o mesmo artigo), `seen_ids` garante que ele aparece apenas uma vez no output final. Evita que o agente leia a mesma resposta duas vezes e confunda repeticao com corroboracao.

#### Conversao distancia para score

```python
score = 1.0 - float(distance)
```

Converte cosine distance (0=identico, 1=oposto) em similarity score (1=identico, 0=oposto) — mais intuitivo para o agente interpretar no output.

---

### Formatacao do output (linhas 88-108)

```python
if not all_results:
    return "Nothing found in answer store for these queries. Try searching the web."

lines = [f"Found {len(all_results)} relevant answers:"]
for i, res in enumerate(all_results, start=1):
    score_fmt = f"{res['score']:.2f}"
    lines.append(f'{i}. [Score: {score_fmt}] Q: "{res["question"]}"')
    answer_lines = res["answer"].strip().splitlines()
    if answer_lines:
        lines.append(f"   A: {answer_lines[0]}")
        for extra_line in answer_lines[1:]:
            lines.append(f"      {extra_line}")
    else:
        lines.append("   A: (empty)")

return "\n".join(lines)
```

| Linha(s) | Explicacao |
|---|---|
| `"Nothing found... Try searching the web."` | Mensagem de fallback explicita que guia o agente para o proximo passo sem ambiguidade. |
| `f"Found {len(all_results)} relevant answers:"` | Header com contagem — o agente sabe imediatamente quantas respostas recebeu. |
| `score_fmt = f"{res['score']:.2f}"` | Score a 2 casas decimais: `0.90`, nao `0.9047382`. |
| `Q: "{res["question"]}"` | Mostra a **pergunta original** guardada no metadata — nao a query que o agente enviou. Permite avaliar se o match e de facto relevante. |
| `answer_lines[0]` + indent `extra_line` | Respostas multi-linha ficam indentadas sob `A:`, mantendo estrutura visual legivel para o LLM. |
| `"   A: (empty)"` | Guard para `content` vazio (nunca deve acontecer em producao, mas protege contra dados corrompidos). |

**Exemplo de output com 2 resultados:**

```
Found 2 relevant answers:

1. [Score: 0.90] Q: "how to find sql injection in login form"
   A: Confirmed SQL injection via 'username' parameter. Use: ' OR '1'='1
      Tested on target 10.0.0.1 on 2024-11-15. Works with SQLMap --forms flag.

2. [Score: 0.83] Q: "login bypass techniques"
   A: Basic auth bypass: admin/admin. If fails, try admin/' OR 1=1--
```

---

### Tratamento de erros (linhas 110-111)

```python
except Exception as exc:
    return f"search_answer tool error: {exc}"
```

Qualquer falha (DB timeout, pgvector indisponivel, embedding API error) retorna uma string descritiva. O agente LLM ve o erro no contexto e pode **decidir ir para a web** em vez de crashar. Nunca `raise` — a continuacao do loop LangGraph depende da tool retornar sempre uma string.

---

## `VectorStore` — Tabela Consultada

A tool consulta directamente o modelo SQLAlchemy `VectorStore` definido em `src/pentest/database/models.py`:

```python
class VectorStore(Base):
    __tablename__ = "vector_store"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_vector_store_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_vector_store_metadata_doc_type", text("(metadata_->>'doc_type')")),
    )
```

### Campos relevantes para a `search_answer` tool

| Campo | Tipo SQL | Relevancia |
|---|---|---|
| `id` | `bigint` | Usado para deduplicacao via `seen_ids` set. |
| `content` | `text` | A resposta guardada — aparece no output como `A: ...`. |
| `metadata_` | `jsonb` | Contem `doc_type`, `answer_type`, `question`, `flow_id`, `task_id`. A tool filtra por `doc_type` e `answer_type`, e le `question` para o output. |
| `embedding` | `vector(1536)` | Vector de embedding `text-embedding-3-small`. A tool calcula `cosine_distance(query_vector)` contra este campo. |

### Indices que aceleram a query

```
┌──────────────────────────────────────────────────────────────────────┐
│ ix_vector_store_embedding_ivfflat                                    │
│   postgresql_using="ivfflat", ops="vector_cosine_ops"                │
│   → ANN (Approximate Nearest Neighbor) para cosine distance          │
│   → Sem este indice, a query faria full table scan O(n)              │
├──────────────────────────────────────────────────────────────────────┤
│ ix_vector_store_metadata_doc_type                                    │
│   expression: (metadata_->>'doc_type')                               │
│   → Filtra rapidamente por doc_type="answer" antes do ANN scan       │
│   → Sem este indice, PostgreSQL scanaria todos os documentos          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Exemplo Completo

### Cenario: Searcher procura tecnicas de bypass de WAF antes de ir para a web

```
Entrada do LLM:
{
  "questions": ["cloudflare bypass pentest", "WAF evasion nginx"],
  "type": "guide",
  "message": "Check if we already found WAF bypass techniques in previous scans"
}

Passo 1: SearchAnswerAction valida input
  → questions: ["cloudflare bypass pentest", "WAF evasion nginx"] ✓
  → type: "guide" ✓ (literal valido)
  → message: "Check if..." ✓

Passo 2: search_answer() executa
  → db_session: nao None ✓
  → OPENAI_API_KEY: sk-abc123 ✓
  → embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

Passo 3: Query 1 — "cloudflare bypass pentest"
  → aembed_query("cloudflare bypass pentest") → vector [0.02, -0.11, ..., 0.08]  (1536 dims)
  → SQL:
      SELECT vector_store.*, embedding <=> [0.02, ...] AS distance
      FROM vector_store
      WHERE metadata_->>'doc_type' = 'answer'
        AND metadata_->>'answer_type' = 'guide'
        AND embedding <=> [0.02, ...] <= 0.2
      ORDER BY distance
      LIMIT 3
  → Resultado: 1 row (id=42, distance=0.08)
    → seen_ids = {42}
    → score = 1.0 - 0.08 = 0.92
    → all_results = [{"question": "cloudflare bypass", "answer": "User-Agent rotation...", "score": 0.92}]

Passo 4: Query 2 — "WAF evasion nginx"
  → aembed_query("WAF evasion nginx") → vector [0.01, -0.09, ..., 0.12]
  → SQL: mesma estrutura, threshold 0.2
  → Resultado: 2 rows (id=42, distance=0.11) e (id=99, distance=0.17)
    → id=42 ja em seen_ids → IGNORADO (deduplicado)
    → id=99 novo → score = 1.0 - 0.17 = 0.83
    → all_results agora tem 2 items

Passo 5: Formatacao
  → "Found 2 relevant answers:"
  → "1. [Score: 0.92] Q: "cloudflare bypass"
       A: User-Agent rotation + 2s delay worked against Cloudflare WAF..."
  → "2. [Score: 0.83] Q: "nginx WAF bypass guide"
       A: Chunked encoding bypasses mod_security in nginx <1.25..."

Saida:
Found 2 relevant answers:

1. [Score: 0.92] Q: "cloudflare bypass"
   A: User-Agent rotation + 2s delay worked against Cloudflare WAF on scan flow_id=7.

2. [Score: 0.83] Q: "nginx WAF bypass guide"
   A: Chunked encoding bypasses mod_security in nginx <1.25. Payload: Transfer-Encoding: chunked
      Tested on target 192.168.1.1 in scan flow_id=5.
```

O Searcher ve estas respostas e decide: "Ja temos guides de scans anteriores — vou usar esta info directamente em vez de ir para a web." Poupa 2 API calls ao Tavily/DuckDuckGo e reduz latencia da subtask.

---

## Diagrama de Fluxo

```
create_search_answer_tool(db_session)
          │
          ├─► db_session is None?
          │         YES → retorna tool que responde "vector store not available"
          │         NO  ↓
          │
          └─► retorna search_answer (BaseTool com db_session capturado em closure)

────────────────────────────────────────────────────────────────

Agent LLM chama search_answer(questions, type, message)
          │
          ├─► db_session is None?  → "vector store not available"
          │
          ├─► OPENAI_API_KEY nao configurado? → "embeddings not configured - set OPENAI_API_KEY"
          │
          ├─► Para cada question em questions (max 5):
          │         │
          │         ├─► aembed_query(question) → query_vector [f32 x 1536]
          │         │
          │         ├─► SQL: SELECT row, cosine_distance AS dist
          │         │         WHERE doc_type='answer' AND answer_type=type AND dist<=0.2
          │         │         ORDER BY dist LIMIT 3
          │         │
          │         └─► Para cada row retornada:
          │                   ├─► id ja em seen_ids? → SKIP (dedup)
          │                   └─► adiciona a all_results com score = 1.0 - dist
          │
          ├─► all_results vazio? → "Nothing found... Try searching the web."
          │
          └─► Formata output: "Found N relevant answers:\n1. [Score: X] Q: ... A: ..."
```

---

## Padrao de Implementacao

A US-058 estabelece o padrao para **tools que acedem a estado partilhado (DB session) via factory + closure**:

1. **Factory `create_X_tool(dep) -> BaseTool`**: recebe a dependencia como argumento, captura-a em closure.
2. **Graceful degradation para `None`**: se a dependencia nao esta disponivel, a tool retorna mensagem descritiva — nunca crash.
3. **Verificacoes em runtime** (nao na factory): `OPENAI_API_KEY` e lido dentro da closure para suportar mudancas de env sem reiniciar.
4. **Erros como string**: `except Exception as exc: return f"... error: {exc}"`. O LLM ve o erro e pode pivotar para outra ferramenta.
5. **Deduplicacao via `seen_ids`**: quando multiplas queries podem retornar o mesmo documento, manter um set de IDs vistos e verificar antes de adicionar ao resultado.

Este padrao e replicado em `create_searcher_tool()` (US-060) e em qualquer tool que precise de sessao de DB.

---

## Questoes Frequentes

### P: Por que threshold `0.2` (cosine distance) e nao `0.8` como no Go?

A: Sao matematicamente equivalentes. Cosine similarity e `1 - cosine_distance`. O Go usa o wrapper LangChain que expoe `ScoreThreshold` como similarity (0.8 = "pelo menos 80% similar"). O SQLAlchemy pgvector expoe `cosine_distance` directamente. `distance <= 0.2` e o mesmo que `similarity >= 0.8` — a mesma fronteira, mas expressa do lado oposto.

### P: Por que `text("metadata_->>'doc_type' = 'answer'")` em vez de ORM filter?

A: A coluna `metadata_` e do tipo `JSON` no SQLAlchemy, e o operador pgvector `->>` (extrai valor JSONB como texto) nao tem wrapper ORM directo. O `text()` permite usar SQL nativo. O risco de SQL injection e mitigado porque `'answer'` e um literal hard-coded, e o `atype` e passado via `.bindparams()` (parametrizado).

### P: O que acontece se o embedding model mudar entre scans?

A: Os embeddings ficam incompativeis. Um vector de `text-embedding-3-small` nao pode ser comparado com um de `text-embedding-ada-002` — a distancia coseno seria sem significado. Na v1 assume-se modelo fixo. A mitigacao futura e guardar `embedding_model` no `metadata_` e filtrar tambem por esse campo.

### P: Por que `del message`?

A: O `message` e parte do contrato do schema (todos os actions no Searcher tem `message` para auditabilidade). Mas dentro da tool, so e usado para logging externo — nao afecta a query nem o output. O `del` suprime avisos de linter sobre variavel declarada mas nao usada.

### P: Porque e que a `search_answer` e `async`?

A: Porque `aembed_query()` (OpenAI API call) e `db_session.execute()` (PostgreSQL query) sao operacoes I/O. Com `async/await`, o event loop pode processar outras coroutines enquanto aguarda estas chamadas. Numa ferramenta sincrona, o processo inteiro bloquearia durante o embedding + query.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-054-SEARCH-MODELS-EXPLAINED]] — define `SearchAnswerAction` e os restantes modelos do Searcher
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]] — barrier tool `search_result` que completa o ciclo do Searcher
- [[US-056-DUCKDUCKGO-SEARCH-TOOL-EXPLAINED]] — motor web alternativo quando vector store nao tem resposta
- [[US-057-TAVILY-SEARCH-TOOL-EXPLAINED]] — motor web preferido com API key
- [[US-008-CORE-DB-MODELS]] — define `VectorStore` e o schema da tabela `vector_store`
