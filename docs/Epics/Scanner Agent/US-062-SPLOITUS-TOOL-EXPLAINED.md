---
tags: [epic, scanner, sploitus, docs]
---

# Deep Dive: US-062 - Sploitus Search Tool

Esta User Story implementa a ferramenta `sploitus`, permitindo que o **Scanner Agent** busque por exploits e ferramentas de segurança diretamente no Sploitus.com.

## Decisões de Arquitetura

1.  **Modelo de Argumentos**: Criamos `SploitusAction` em `src/pentest/models/tool_args.py` para validar a query, o tipo de exploit, a ordenação e o limite de resultados. 
    *   **Clamping**: Implementamos clamping dinâmico para `max_results` (entre 10 e 25) via `field_validator` para evitar falhas de validação por limites de range.
2.  **Comunicação HTTP**: Utilizamos `httpx.AsyncClient` para realizar requisições assíncronas ao endpoint de busca do Sploitus. O client usa validação TLS padrão para segurança.
3.  **Mimetismo de Browser**: Foram configurados headers realistas (`User-Agent`, `Origin`, `Referer`) para evitar bloqueios simples e garantir a compatibilidade com a API pública do Sploitus.
4.  **Disponibilidade Condicional**: A ferramenta pode ser desativada via variável de ambiente `SPLOITUS_ENABLED`.
5.  **Resiliência e Erros**: Erros de rede, timeouts (30s), rate limits (HTTP 422/499) e falhas de JSON são capturados e retornados como strings informativas.
6.  **Formatação de Output**: Os resultados são formatados em Markdown numerado, incluindo:
    *   Header com **Type** e **Total matches**.
    *   Campos específicos: **Language** para exploits e **Download URL** para tools.
7.  **Truncagem de Dados**:
    *   **Snippet de Source**: Cada resultado tem seu campo `source` truncado para 500 caracteres.
    *   **Output Global**: O output total da ferramenta é truncado para 16.000 caracteres (`MAX_OUTPUT_LENGTH`) para economizar tokens de contexto.

## Modelo SploitusAction

| Campo | Tipo | Descrição | Validação |
| :--- | :--- | :--- | :--- |
| `query` | `str` | Termo de busca (exploit ou ferramenta). | Obrigatório, não vazio. |
| `exploit_type` | `Literal` | "exploits" ou "tools". | Default: "exploits". |
| `sort` | `Literal` | "default", "date" ou "score". | Default: "default". |
| `max_results` | `int` | Número máximo de resultados. | Clamped: 10 a 25. |
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

## Related Notes

* [[USER-STORIES]]
* [[AGENT-ARCHITECTURE]]
