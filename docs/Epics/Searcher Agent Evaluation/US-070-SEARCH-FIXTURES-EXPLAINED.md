---
tags: [SearcherAgent, Evals]
---

# US-070: Search Fixtures & Controlled Corpus — Explicacao Detalhada

Esta documentacao descreve a implementacao de um sistema de fixtures e corpus controlado para o agente de busca (Searcher Agent), visando avaliacoes deterministicas e isoladas de mudancas na internet.

## Contexto

A avaliacao de agentes que dependem de busca na web e instavel por natureza. Para permitir testes e benchmarks confiaveis, implementamos:
1. Uma estrutura de arquivos para armazenar registros de buscas (`fixtures`).
2. Um interceptador (`SearcherFixtureInterceptor`) que simula chamadas de ferramentas de busca com base em correspondencia de padroes.
3. Um extrator para converter registros de execucoes passadas em fixtures reutilizaveis.

## Ficheiros Implementados

| Arquivo | Descricao |
| :--- | :--- |
| **`tests/evals/searcher/interceptor.py`** | Lógica de interceptação e mock de ferramentas. |
| **`tests/evals/searcher/extract_search_fixtures.py`** | Script de extração de registros para fixtures. |
| **`tests/evals/searcher/test_fixtures.py`** | Suite de testes unitários do sistema de fixtures. |

## Detalhes de Implementacao

### 1. Interceptador (`tests/evals/searcher/interceptor.py`)

A classe `SearcherFixtureInterceptor` gerencia a correspondência entre chamadas de ferramentas e respostas gravadas.

```python
class SearcherFixtureInterceptor:
    def intercept(self, tool_name: str, args: Dict[str, Any]) -> Any:
        # Preserve search_result (do not mock)
        if tool_name == "search_result":
            return None 
            
        # Tenta encontrar correspondencia
        for fixture in self.fixtures:
            if fixture["tool_name"] == tool_name and re.match(fixture["args_pattern"], normalized_args):
                return fixture["response"]
        
        # Fallback para chamadas nao correspondidas
        return self._get_fallback(tool_name)
```

- **Por que é assim?**: A preservação de `search_result` é essencial para que o fluxo de decisão do agente continue funcionando em testes de avaliação, garantindo que o mock apenas substitua as fontes de informação, não o processo de decisão.

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[Epics/Searcher Agent Evaluation/NOTE-HUB|Searcher Evaluation Hub]]
