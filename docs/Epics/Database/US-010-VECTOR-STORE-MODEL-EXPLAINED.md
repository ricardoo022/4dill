---
tags: [database]
---

# US-010: Vector Store Model (pgvector) — Explicacao Detalhada

Este documento explica as alteracoes feitas em `src/pentest/database/models.py`, `tests/unit/database/test_models.py`, `tests/integration/database/test_models.py` e `tests/e2e/database/test_models_e2e.py` para implementar o US-010 com armazenamento vetorial, filtros por metadata e validacao end-to-end em PostgreSQL real.

---

## Contexto

- O runtime precisava de uma tabela vetorial para memoria semantica, alinhada com o ecossistema `pgvector` e com o uso futuro de LangChain `PGVector`.
- O US-010 exige duas partes em simultaneo: **modelo SQLAlchemy** (schema + indices) e **prova funcional** (query de similaridade, filtros, rejeicao de dimensao invalida).
- A implementacao foi feita no mesmo modulo de modelos para manter coesao com a hierarquia de `Flow/Task/Subtask` e com os modelos de auditoria (`Toolcall`, `Msgchain`, `Msglog`, `Termlog`).
- Foi adicionado um helper explicito para extensao (`create_vector_extension`) para garantir bootstrap idempotente em bases novas.
- A estrategia de testes foi distribuida em 3 camadas:
  - unit: estrutura declarativa do modelo,
  - integration: round-trip com DB real,
  - e2e: comportamento completo de lifecycle (insert/search/delete) e validacoes de catalogo (`pg_indexes`, `pg_extension`).

---

## `create_vector_extension` e `VectorStore` (`src/pentest/database/models.py`)

```python
async def create_vector_extension(connection: AsyncConnection) -> None:
    """Ensure pgvector extension is installed in the current database."""

    await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


class VectorStore(Base):
    """Vector memory store for semantic search over runtime documents."""

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
        Index("ix_vector_store_metadata_flow_id", text("(metadata_->>'flow_id')")),
        Index("ix_vector_store_metadata_task_id", text("(metadata_->>'task_id')")),
        Index("ix_vector_store_metadata_doc_type", text("(metadata_->>'doc_type')")),
    )
```

| Linha(s) | Explicacao |
|---|---|
| `62-65` | Helper assíncrono idempotente para garantir `CREATE EXTENSION ... IF NOT EXISTS` sem depender de migrations neste US. |
| `480-488` | Schema principal do vector store: texto fonte (`content`), metadata JSON (`metadata_`), embedding 1536-d e timestamp timezone-aware. |
| `491-496` | Indice ANN com `ivfflat` e operador `vector_cosine_ops`, alinhado com requisito de busca por similaridade por cosseno. |
| `497-499` | Indices de expressao JSON para filtros frequentes (`flow_id`, `task_id`, `doc_type`) sem full scan da coluna JSON completa. |

### Campos do `VectorStore`

| Campo | Tipo | Default/Constraint | Descricao |
|---|---|---|---|
| `id` | `BigInteger` | `primary_key=True`, `autoincrement=True` | Identificador unico da linha vetorial. |
| `content` | `Text` | `nullable=False` | Conteudo bruto que foi embedado (saidas de tools, contexto, respostas). |
| `metadata_` | `JSON` | `default=dict`, `nullable=False` | Metadados para escopo de busca (`flow_id`, `task_id`, `doc_type`, etc.). |
| `embedding` | `Vector(1536)` | `nullable=False` | Vetor pgvector na dimensionalidade exigida pelo US-010. |
| `created_at` | `TimestampTZ` | `server_default=now()`, `nullable=False` | Momento de insercao para auditoria/ordenacao temporal. |

### Porque e assim?

- O nome `metadata_` (com underscore) evita colisao semantica com palavra comum de metadados em Python.
- `ivfflat` foi escolhido como baseline simples e barato para o volume inicial (nota tecnica do US).
- O helper de extensao no modulo de modelos reduz friccao em testes e bootstrap local enquanto US-011 (migrations) nao consolida tudo.

---

## Testes Unitarios do Modelo (`tests/unit/database/test_models.py`)

```python
class TestVectorStoreModel:
    """Unit tests for VectorStore model structure."""

    def test_vector_store_tablename(self):
        assert VectorStore.__tablename__ == "vector_store"

    def test_vector_store_has_all_columns(self):
        mapper = inspect(VectorStore)
        column_names = {col.key for col in mapper.columns}
        assert {"id", "content", "metadata_", "embedding", "created_at"}.issubset(column_names)

    def test_vector_store_embedding_dimension(self):
        mapper = inspect(VectorStore)
        embedding_col = mapper.columns["embedding"]
        assert getattr(embedding_col.type, "dim", None) == 1536

    def test_vector_store_metadata_default(self):
        mapper = inspect(VectorStore)
        metadata_col = mapper.columns["metadata_"]
        assert metadata_col.default is not None

    def test_vector_store_has_complete_expected_indexes(self):
        table_args = VectorStore.__table_args__
        if isinstance(table_args, tuple):
            index_names = {idx.name for idx in table_args if isinstance(idx, Index)}
            assert index_names == {
                "ix_vector_store_embedding_ivfflat",
                "ix_vector_store_metadata_flow_id",
                "ix_vector_store_metadata_task_id",
                "ix_vector_store_metadata_doc_type",
            }
```

| Linha(s) | Explicacao |
|---|---|
| `780-785` | Verifica nome de tabela consistente com o contrato do US. |
| `786-790` | Garante que o mapper declara os 5 campos obrigatorios. |
| `792-795` | Prova estrutural da dimensionalidade (`1536`) no tipo de coluna. |
| `797-800` | Garante default para metadata, evitando `NULL` acidental em inserts sem metadata explicita. |
| `802-811` | Valida conjunto completo de indices declarativos esperado no modelo. |

---

## Testes de Integracao (`tests/integration/database/test_models.py`)

```python
# schema setup (excerpt)
await conn.execute(text("DROP TABLE IF EXISTS vector_store CASCADE;"))
...
await create_vector_extension(conn)
await conn.run_sync(Base.metadata.create_all)

# cleanup (excerpt)
await session.execute(text("DELETE FROM vector_store"))
```

```python
async def test_vector_store_create_and_similarity_query(db_session) -> None:
    ...
    result = await session.execute(
        select(VectorStore)
        .order_by(VectorStore.embedding.cosine_distance(query_vector))
        .limit(3)
    )
    nearest = result.scalars().all()
    assert nearest[0].content == "base"
    assert {doc.content for doc in nearest}.issuperset({"base", "near"})
```

```python
async def test_vector_store_wrong_dimension_rejected(db_session) -> None:
    ...
    with pytest.raises(StatementError, match="expected 1536 dimensions"):
        await session.flush()
```

| Bloco | Explicacao |
|---|---|
| Fixture de schema | Inclui `vector_store` no ciclo drop/create e executa helper da extensao antes de `create_all`. |
| `test_vector_extension_exists` | Confirma presenca da extensao em `pg_extension`. |
| `test_vector_store_create_and_similarity_query` | Round-trip semantico com `cosine_distance`. |
| `test_vector_store_metadata_filtering` | Prova filtros por `flow_id`, `task_id` e `doc_type` via expressoes JSON. |
| `test_vector_store_insert_many_and_ordered_similarity` | Testa comportamento com volume maior (100 linhas) para ordenar nearest neighbor. |
| `test_vector_store_wrong_dimension_rejected` | Prova caminho de erro para embedding invalido (768). |

### Porque e assim?

- Os testes de integracao rodam com infraestrutura real para validar comportamento de `pgvector` (nao apenas declaracao SQLAlchemy).
- O match de excecao (`expected 1536 dimensions`) protege contra regressao silenciosa de validacao de dimensão.

---

## Testes End-to-End de US-010 (`tests/e2e/database/test_models_e2e.py`)

```python
async def test_us010_vector_store_insert_search_delete_e2e(db_session) -> None:
    embedding = [0.0] * 1536
    embedding[0] = 1.0

    # insert
    ...

    # search
    result = await session.execute(
        select(VectorStore)
        .where(text("metadata_->>'flow_id' = '77'"))
        .order_by(VectorStore.embedding.cosine_distance(embedding))
        .limit(1)
    )
    fetched = result.scalar_one()
    assert fetched.id == row_id

    # delete
    delete_result = await session.execute(delete(VectorStore).where(VectorStore.id == row_id))
    assert delete_result.rowcount == 1

    # verify deleted
    result = await session.execute(select(VectorStore).where(VectorStore.id == row_id))
    assert result.scalar_one_or_none() is None
```

```python
async def test_us010_vector_index_uses_ivfflat_cosine_ops_e2e(db_session) -> None:
    result = await session.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'vector_store'
              AND indexname = 'ix_vector_store_embedding_ivfflat'
            """
        )
    )
    indexdef = result.scalar_one()
    assert "USING ivfflat" in indexdef
    assert "vector_cosine_ops" in indexdef
```

| Teste E2E | Objetivo |
|---|---|
| `test_us010_vector_store_similarity_and_metadata_filters_e2e` | Similaridade + filtro por `flow_id` em DB real. |
| `test_us010_vector_store_insert_search_delete_e2e` | Lifecycle completo: insert -> search -> delete -> confirmacao de remocao. |
| `test_us010_vector_extension_idempotent_e2e` | Idempotencia do helper de extensao em execucoes repetidas. |
| `test_us010_vector_index_uses_ivfflat_cosine_ops_e2e` | Verificacao de definicao fisica do indice no catalogo PostgreSQL. |
| `test_us010_vector_store_metadata_task_and_doc_type_filters_e2e` | Cobertura adicional de filtros por `task_id` e `doc_type`. |
| `test_us010_vector_store_wrong_dimension_rejected_e2e` | Rejeicao de dimensão invalida no caminho e2e. |

---

## Exemplo Completo

Step 1: Setup de schema e extensao
  -> input: DB limpo
  -> output: `vector` extension instalada + `vector_store` criada

Step 2: Insercao de documentos vetoriais
  -> input: `content`, `metadata_`, `embedding[1536]`
  -> output: linhas persistidas com `id` e `created_at`

Step 3: Pesquisa semantica
  -> input: vetor de query + `ORDER BY cosine_distance`
  -> output: nearest neighbors ordenados por similaridade

Step 4: Filtros por metadata
  -> input: predicados JSON (`flow_id`, `task_id`, `doc_type`)
  -> output: subconjunto de documentos por escopo operacional

Step 5: Validacao de erro
  -> input: embedding inválido (768)
  -> output: erro de validacao de dimensão

Fluxo de controlo (US-010)

```text
┌──────────────────────────────────────────────────────────┐
│ create_vector_extension(conn)                           │
└───────────────────────────────┬──────────────────────────┘
                                │
                                v
                 ┌─────────────────────────────┐
                 │ INSERT vector_store row     │
                 │ embedding dim == 1536 ?     │
                 └──────────────┬──────────────┘
                                │
                  ┌─────────────┴─────────────┐
                  │                           │
                  v                           v
        ┌──────────────────────┐    ┌─────────────────────────────┐
        │ valid vector         │    │ invalid vector              │
        │ persist row          │    │ raise dimension error       │
        └──────────┬───────────┘    └─────────────────────────────┘
                   │
                   v
      ┌──────────────────────────────────────────────┐
      │ query cosine_distance + metadata filters     │
      └───────────────────┬──────────────────────────┘
                          │
                          v
               ┌─────────────────────────┐
               │ assert nearest/results  │
               └──────────┬──────────────┘
                          │
                          v
               ┌─────────────────────────┐
               │ delete + verify absent  │
               └─────────────────────────┘
```

---

## Ficheiros alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/database/models.py` | Adiciona helper `create_vector_extension` e modelo `VectorStore` com índices ANN/metadata. |
| `tests/unit/database/test_models.py` | Valida contrato estrutural do `VectorStore` (schema, dimensão e índices). |
| `tests/integration/database/test_models.py` | Prova comportamento real de pgvector: extensão, similaridade, filtros, volume e erro de dimensão. |
| `tests/e2e/database/test_models_e2e.py` | Executa cenarios end-to-end completos, incluindo lifecycle insert/search/delete e inspeção de catálogo PostgreSQL. |

---

## Related Notes

- [Docs Home](../../README.md)
- [[DATABASE-SCHEMA]]
- [[USER-STORIES]]
- [[Epics/Database/US-009-SUPPORTING-DB-MODELS-EXPLAINED]]
- [[Epics/Database/US-008-CORE-DB-MODELS]]
