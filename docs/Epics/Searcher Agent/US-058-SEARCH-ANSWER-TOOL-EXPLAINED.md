---
tags: [agents]
---

# US-058: search_answer tool (pgvector read) - EXPLAINED

## Architecture Decisions
- **Factory Pattern**: The tool is created via `create_search_answer_tool(db_session)` to allow dependency injection of the database session, facilitating testing and runtime flexibility.
- **Pgvector Integration**: Uses `sqlalchemy-pgvector`'s `cosine_distance` for similarity search directly in the database.
- **Metadata Filtering**: Strictly filters by `doc_type="answer"` and `answer_type` provided by the agent to ensure high-quality results.
- **Deduplication**: Implements a `seen_ids` set to ensure the same document isn't returned multiple times when multiple questions are provided.
- **Error Handling**: Gracefully handles missing database sessions, missing API keys, and database errors by returning informative strings to the LLM.

## Implementation Details
- **Model**: `VectorStore` (SQLAlchemy 2.0).
- **Embedding**: `text-embedding-3-small` (1536 dimensions).
- **Threshold**: Cosine distance <= 0.2 (equivalent to >= 0.8 similarity).
- **Limit**: Max 3 results per question.

## How to run tests
### Unit Tests
```bash
pytest tests/unit/tools/test_search_memory_unit.py -v
```

### Integration Tests
Requires a running PostgreSQL with `pgvector` extension.
```bash
pytest tests/integration/tools/test_search_memory_integration.py -v
```

## Related Notes

- [README](README.md)
- [[USER-STORIES]]
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
