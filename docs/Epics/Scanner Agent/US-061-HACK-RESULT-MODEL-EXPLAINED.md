---
tags: [agents]
---

# Deep Dive: US-061 - HackResult Model & Barrier Tool

Esta User Story define o contrato de dados entre o **Scanner Agent** e o **Orchestrator**. O objetivo é garantir que os resultados do escaneamento sejam retornados de forma estruturada e validada.

## Decisões de Arquitetura

1.  **Modelo de Dados (Pydantic)**: Utilizamos `HackResult` para encapsular a saída do agente.
    *   `result`: Contém o relatório técnico detalhado (em inglês), destinado a ser processado por outros agentes ou armazenado como evidência.
    *   `message`: Um resumo curto para fins de log e orquestração rápida.
2.  **Validação Estrita**: Ambos os campos possuem validadores que impedem strings vazias ou compostas apenas por espaços em branco, garantindo a integridade dos dados trafegados no grafo.
3.  **Mecanismo de Barreira**: A ferramenta `hack_result` atua como um "fim de linha" para o agente Scanner. Quando esta ferramenta é chamada, o `BarrierAwareToolNode` interrompe o loop do agente e extrai os argumentos do `HackResult` para o estado global do grafo.

## Modelo HackResult

| Campo | Tipo | Descrição | Validação |
| :--- | :--- | :--- | :--- |
| `result` | `str` | Relatório técnico detalhado em inglês. | Não vazio, strip aplicado. |
| `message` | `str` | Resumo curto interno para orquestração. | Não vazio, strip aplicado. |

## Ferramenta hack_result

A ferramenta é registrada no `src/pentest/tools/barriers.py` e utiliza o schema do `HackResult`.

**Referência PentAGI**: Este modelo alinha-se com a estrutura de saída esperada no backend do PentAGI (`backend/pkg/tools/args.go`), facilitando a integração futura.

## Como executar os testes

Para validar a implementação do modelo e da ferramenta, execute:

```bash
pytest tests/unit/models/test_hack.py -v
pytest tests/unit/tools/test_barriers.py -v
```

Para validar a tipagem e o linting:

```bash
mypy src/pentest/models/hack.py
ruff check src/pentest/models/hack.py
```

## Related Notes

- [[US-062-SPLOITUS-TOOL-EXPLAINED]] — Sploitus search tool, primeira ferramenta do Scanner agent
- [[US-038-BARRIERS-EXPLAINED]] — padrão barrier tool (subtask_list, search_result, hack_result)
- [[US-037-BASE-GRAPH-EXPLAINED]] — BarrierAwareToolNode, como as barreiras interrompem o loop
- [[US-054-SEARCH-MODELS-EXPLAINED]] — SearchResult e SearchAction, estrutura análoga no Searcher
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]] — coexistência de subtask_list e search_result
