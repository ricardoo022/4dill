# Deep Dive: US-062 - Sploitus Search Tool

Esta User Story implementa a ferramenta `sploitus`, permitindo que o **Scanner Agent** busque por exploits e ferramentas de segurança diretamente no Sploitus.com.

## Decisões de Arquitetura

1.  **Modelo de Argumentos**: Criamos `SploitusAction` em `src/pentest/models/tool_args.py` para validar a query, o tipo de exploit, a ordenação e o limite de resultados (máximo 25).
2.  **Comunicação HTTP**: Utilizamos `httpx.AsyncClient` para realizar requisições assíncronas ao endpoint de busca do Sploitus.
3.  **Mimetismo de Browser**: Foram configurados headers realistas (`User-Agent`, `Origin`, `Referer`) para evitar bloqueios simples e garantir a compatibilidade com a API pública do Sploitus.
4.  **Resiliência e Erros**: Erros de rede, timeouts (30s) e rate limits (HTTP 422/499) são capturados e retornados como strings informativas, seguindo o padrão do projeto onde o LLM decide como reagir ao erro.
5.  **Formatação de Output**: Os resultados são formatados em Markdown numerado, incluindo título, URL, data e score (quando disponível).
6.  **Truncagem de Dados**:
    *   **Snippet de Source**: Cada resultado tem seu campo `source` truncado para 500 caracteres.
    *   **Output Global**: O output total da ferramenta é truncado para 16.000 caracteres (`MAX_OUTPUT_LENGTH`) para economizar tokens de contexto.

## Modelo SploitusAction

| Campo | Tipo | Descrição | Validação |
| :--- | :--- | :--- | :--- |
| `query` | `str` | Termo de busca (exploit ou ferramenta). | Obrigatório, não vazio. |
| `exploit_type` | `Literal` | "exploits" ou "tools". | Default: "exploits". |
| `sort` | `Literal` | "default", "date" ou "score". | Default: "default". |
| `max_results` | `int` | Número máximo de resultados. | 1 a 25. |
| `message` | `str` | Resumo do objetivo da pesquisa. | Obrigatório. |

## Como executar os testes

Para validar a ferramenta, execute:

```bash
pytest tests/unit/tools/test_sploitus.py -v
```

Para validar a tipagem e o linting:

```bash
mypy src/pentest/tools/sploitus.py
ruff check src/pentest/tools/sploitus.py
```
