---
tags: [evaluation, searcher, agent, langsmith, infrastructure]
---

# US-068: Searcher Agent Evaluation Infrastructure — Explicacao Detalhada

Este documento detalha a implementação da infraestrutura de avaliação (evals) para o agente Searcher, incluindo a recolha de traços de execução (trajectories), o suporte para callbacks no agente, e os scripts de gravação e avaliação. Ficheiros explicados: `src/pentest/agents/searcher.py`, `tests/evals/searcher/record_search_run.py`, `tests/evals/searcher/run_searcher_eval.py` e `tests/evals/searcher/test_infra.py`.

## Contexto

Para garantir que o Searcher Agent toma boas decisões de pesquisa e seleção de links de forma consistente, é necessário um mecanismo rigoroso de avaliação. A infraestrutura de evals permite-nos executar o agente contra um dataset de perguntas conhecidas e comparar as suas respostas (e, mais importante, as *trajetórias* ou chamadas de ferramentas) com resultados esperados. Este US introduz a camada base para esse processo, que envolve:
1. Modificar o agente para aceitar callbacks de LangChain.
2. Criar um script para gravar uma execução completa e guardar o seu *trace*.
3. Estruturar os diretórios e a pipeline de avaliação com LangSmith.
4. Escrever testes automatizados que garantem que o sistema de avaliação funciona de forma estanque.

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|----------|------------------|
| `src/pentest/agents/searcher.py` | Modificado para aceitar o parâmetro `callbacks` e passá-lo para a execução do grafo LangGraph. |
| `tests/evals/searcher/record_search_run.py` | Script que invoca o Searcher Agent e utiliza o `TrajectoryCallbackHandler` para escutar e gravar os `tool_calls` e as interações. |
| `tests/evals/searcher/run_searcher_eval.py` | Script que itera por um dataset e lança as instâncias de avaliação contra o LangSmith ou infraestrutura local. |
| `tests/evals/searcher/test_infra.py` | Suite de testes para assegurar que a execução dos scripts de eval (e a geração de JSONs) decorre sem erros. |

---

## Modificações no Searcher Agent (`src/pentest/agents/searcher.py`)

A função `perform_search` foi estendida para suportar injetar `callbacks` na execução, essencial para inspecionar o que o agente faz por baixo do capô.

```python
async def perform_search(
    question: str,
    llm: Any,
    execution_context: str = "",
    task: str | None = None,
    subtask: str | None = None,
    callbacks: list[Any] | None = None,
) -> str:
# ...
    config = {"callbacks": callbacks} if callbacks else {}
# ...
        result = await agent_graph.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            },
            config=config,
        )
```

### Explicação dos Argumentos (Novos)

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `callbacks` | `list[Any] \| None` | Lista de instâncias de `BaseCallbackHandler` passadas para o LangGraph (via `config`). Permite espiar o início/fim das chamadas ao LLM e ao Tool node. |

**Porque é assim?**
Ao delegarmos o processamento de steps para o LangGraph, a única forma limpa e oficial de inspecionar eventos internos (sem mutar estado global) é através do `config={"callbacks": [...]}`. Estes callbacks disparam assincronamente a cada evento-chave.

---

## Gravação de Execuções (`tests/evals/searcher/record_search_run.py`)

Este script funciona como a porta de entrada para a criação de um golden dataset. Permite introduzir uma questão ao agente e recolher todos os *tool calls*.

```python
class TrajectoryCallbackHandler(AsyncCallbackHandler):
    """Callback handler to record agent trajectories (messages and tool calls)."""

    def __init__(self):
        self.tool_calls: list[dict[str, Any]] = []

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], **kwargs: Any) -> None:
        """Ignore chat model start."""
        pass

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name")
        self.tool_calls.append(
            {
                "name": tool_name,
                "input": input_str,
                "start_time": datetime.now().isoformat(),
            }
        )

    async def on_tool_end(self, output: str, **kwargs) -> None:
        if self.tool_calls:
            self.tool_calls[-1]["output"] = output
            self.tool_calls[-1]["end_time"] = datetime.now().isoformat()
```

### Detalhes de Implementação

| Método | Responsabilidade |
|--------|------------------|
| `on_tool_start` | Disparado pelo LangGraph quando uma ferramenta (ex: `tavily_search`) começa a execução. Guarda o nome e input. |
| `on_tool_end` | Quando a ferramenta termina, enriquece a última chamada de `tool_calls` com o output resultante. |
| `on_chat_model_start` | Implementação vazia (`pass`) introduzida para evitar um `NotImplementedError` por defeito, garantindo estabilidade no LangChain AsyncCallbackHandler. |

---

## Script de Avaliação (`tests/evals/searcher/run_searcher_eval.py`)

Configura a execução de avaliações massivas contra o LangSmith, lidando com inicialização e setup.

```python
from pentest.agents.searcher import perform_search  # noqa: E402
from pentest.providers.factory import create_chat_model  # noqa: E402

load_dotenv()

DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "searcher.json"
```

A alteração do `sys.path` garante que as execuções isoladas ou em subprocessos da infraestrutura de testes encontrem o módulo `pentest`. O `# noqa: E402` é necessário porque as manipulações do sys.path ocorrem antes da importação.

---

## Testes de Infraestrutura (`tests/evals/searcher/test_infra.py`)

Garante a resiliência da infraestrutura de evals e das dependências entre processos.

```python
def test_record_search_run_help():
    """Verify record_search_run.py --help works."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    result = subprocess.run(
        [sys.executable, "tests/evals/searcher/record_search_run.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert "usage: record_search_run.py" in result.stdout
    assert "--question" in result.stdout
```

**Porque é assim?**
Subprocessos não herdam automaticamente as modificações `sys.path` executadas no pytest hook. A injeção do caminho da pasta `src` via a variável de ambiente `PYTHONPATH` foi crucial para resolver um erro `ModuleNotFoundError: No module named 'pentest'`.

---

## Related Notes

- [Docs Home](../../README.md)
- [[AGENT-ARCHITECTURE]]
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[US-060-SEARCHER-AGENT-EXPLAINED|Searcher Agent]]
