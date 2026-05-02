---
tags: [evaluation, agents]
---

# US-047: Generator Eval Runner — Explicacao Detalhada

Este documento explica, em detalhe, a implementacao da `US-047` em `src/pentest/agents/exceptions.py`, `src/pentest/agents/generator.py`, `tests/evals/run_agent_eval.py`, `tests/evals/evaluators/subtask_plan.py`, e `tests/evals/test_run_agent_eval.py`.

---

## Contexto

A `US-047` liga duas partes previamente isoladas do projecto: o agente Generator (implementado na US-044) e o dataset PortSwigger MVP (US-045). O resultado é um CLI runner que:

1. Carrega exemplos do dataset `portswigger_mvp.json`
2. Instancia o Generator para cada exemplo via `generate_subtasks()`
3. Avalia a saída com um evaluator estrutural (`subtask_plan_valid`)
4. Imprime métricas locais **ou** sobe os resultados para LangSmith via `client.evaluate()`

O runner não é código de produção — vive em `tests/evals/` e serve como infraestrutura de avaliação contínua. Não tem equivalente directo no PentAGI Go.

Esta US também introduz `GeneratorError` como excepção tipada para o agente Generator, e `generate_subtasks()` como a função de entrada pública do agente.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `src/pentest/agents/exceptions.py` | Excepção tipada `GeneratorError` |
| `src/pentest/agents/generator.py` | Função `generate_subtasks()` — entry point do agente |
| `tests/evals/run_agent_eval.py` | CLI runner com modo local e LangSmith |
| `tests/evals/evaluators/__init__.py` | Package de evaluators; re-exporta `subtask_plan_valid` |
| `tests/evals/evaluators/subtask_plan.py` | Evaluator estrutural do plano do Generator |
| `tests/evals/test_run_agent_eval.py` | 9 testes (unit + e2e) para o runner e evaluator |

---

## 1) `src/pentest/agents/exceptions.py` — `GeneratorError`

```python
class GeneratorError(Exception):
    """Raised when the Generator agent fails to produce a valid plan."""
```

Uma excepção dedicada ao Generator. Permite que o chamador (`run_agent_eval.py`, futuramente `controller/task.py`) diferencie falhas de planeamento de outros erros de runtime.

**Porque uma classe dedicada e não `RuntimeError`?**
O Generator faz parte de um pipeline com múltiplos agentes. Erros de agente são recuperáveis (ex: retry, Adviser), enquanto outros erros (DB, Docker) são de infraestrutura. Ter `GeneratorError` permite que o chamador use `except GeneratorError` sem apanhar erros de camadas inferiores.

---

## 2) `src/pentest/agents/generator.py` — `generate_subtasks()`

Este módulo é o entry point público do agente Generator — combina carregamento de skills, renderização de prompts, construção de ferramentas, instanciação do grafo LangGraph, e parsing do resultado da barrier.

### Assinatura

```python
def generate_subtasks(
    input: str,
    backend_profile: BackendProfile,
    skills_dir: str,
    docker_client: Any = None,
) -> list[SubtaskInfo]:
```

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `input` | `str` | Objectivo do utilizador (ex: `"scan https://example.com"`) |
| `backend_profile` | `BackendProfile` | Resultado de FASE 0 — tipo de backend, target, scan path |
| `skills_dir` | `str` | Directório raiz com pastas `scan-fase-*` e ficheiros `SKILL.md` |
| `docker_client` | `Any \| None` | Se fornecido, adiciona ferramentas terminal e file (mock); se `None`, omite-as |

**Retorno:** `list[SubtaskInfo]` com 1–15 subtarefas.

**Lança:** `GeneratorError` em qualquer fase de falha.

### Fluxo interno (7 fases)

```
input + backend_profile
        │
        ▼
1. load_fase_index()          ← FASE index para o scan_path
        │
        ▼
2. render_generator_prompt()  ← system + user prompt via Jinja2
        │
        ▼
3. ferramentas base           ← browser, memorist, searcher, subtask_list
   + ferramentas Docker        ← terminal, file (só se docker_client fornecido)
        │
        ▼
4. init_chat_model(model)     ← GENERATOR_MODEL env var (default: gpt-4.1-mini)
        │
        ▼
5. create_agent_graph(...)    ← LangGraph com barrier_names={"subtask_list"}
        │
        ▼
6. graph.invoke(state)        ← SystemMessage + HumanMessage
        │
        ▼
7. barrier_result parsing     ← subtasks → list[SubtaskInfo]
```

### Fase 3 — Ferramentas base vs Docker

```python
browser_tool = create_browser_tool()
tools = [browser_tool, memorist, searcher, subtask_list]

if docker_client is not None:
    terminal_tool = create_mock_terminal_tool()
    file_tool = create_mock_file_tool()
    tools.extend([terminal_tool, file_tool])
```

O Generator usa ferramentas mock de terminal e file quando há `docker_client`. O motivo: o Generator planeia (não executa) — nunca precisa de acesso real ao container. As ferramentas mock evitam que o LLM tente executar comandos durante o planeamento.

Em contexto de eval (`docker_client=None`), terminal e file são completamente omitidos para simplificar o grafo e reduzir latência.

### Fase 4 — Selecção de modelo

```python
model = os.getenv("GENERATOR_MODEL", "gpt-4.1-mini")
llm = init_chat_model(model)
```

`init_chat_model` do LangChain aceita o formato `provider:model` (ex: `anthropic:claude-sonnet-4-6`) ou nome bare reconhecido automaticamente (ex: `gpt-4.1-mini`). O runner de eval passa o valor via env var, permitindo trocar de modelo sem alterar código.

### Fase 7 — Parsing do resultado

```python
barrier_result = result_state.get("barrier_result")

if not barrier_result:
    raise GeneratorError(
        f"Generator failed to produce a plan (barrier not hit). Final message: {final_message}"
    )

subtasks_data = barrier_result.get("subtasks")
if not isinstance(subtasks_data, list):
    raise GeneratorError(...)
if not (1 <= len(subtasks_data) <= 15):
    raise GeneratorError(...)

subtasks = [
    SubtaskInfo(title=st["title"], description=st.get("description", ""), fase=st.get("fase"))
    for i, st in enumerate(subtasks_data)
]
```

O `barrier_result` é populado pelo `BarrierAwareToolNode` quando o LLM chama a tool `subtask_list`. Se a barrier não for atingida (o LLM parou por outro motivo), `barrier_result` é `None` — sinal de que o Generator não produziu um plano válido.

A validação `1 <= len <= 15` reflecte a restrição do prompt do Generator: planos com 0 ou mais de 15 tarefas são considerados malformados.

---

## 3) `tests/evals/run_agent_eval.py` — CLI Runner

### Bootstrap de paths e dotenv

```python
REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv()
```

O runner corre como script directo (`python tests/evals/run_agent_eval.py`). O `sys.path.insert` garante que `tests.evals.evaluators` resolve sem instalar o package. O `load_dotenv()` carrega `.env` automaticamente (necessário para `LANGSMITH_API_KEY`, `OPENAI_API_KEY`, etc.).

### Argumentos CLI

| Flag | Default | Descrição |
|---|---|---|
| `--agent` | (obrigatório) | Agente a avaliar; actualmente só `generator` |
| `--subset` | `quick` | Subset do dataset (ex: `quick`) |
| `--no-upload` | `False` | Executar localmente sem subir ao LangSmith |
| `--runs` | `1` | Número de repetições por exemplo |
| `--skills-dir` | `lusitai-internal-scan/.claude/skills` | Raiz com pastas `scan-fase-*` |

### `_load_examples(subset)` — carregamento do dataset

```python
def _load_examples(subset: str) -> list[dict]:
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    if subset not in dataset["subsets"]:
        available = list(dataset["subsets"].keys())
        print(f"Error: unknown subset '{subset}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    lab_ids = dataset["subsets"][subset]["labs"]
    labs_by_id = {lab["lab_id"]: lab for lab in dataset["labs"]}

    examples = []
    for lab_id in lab_ids:
        lab = labs_by_id[lab_id]
        examples.append({
            "inputs": {
                "lab_id": lab["lab_id"],
                "lab_url": lab["lab_url"],
                "category": lab["category"],
                "expected_vulnerability": lab["expected_vulnerability"],
                "expected_backend_type": lab["expected_backend_type"],
                "fase_phase": lab["fase_phase"],
            },
            "outputs": {
                "expected_vulnerability": lab["expected_vulnerability"],
                "category": lab["category"],
            },
        })
    return examples
```

Cada exemplo tem dois envelopes:

| Chave | Conteúdo | Uso |
|---|---|---|
| `inputs` | Dados que o target recebe | Passados ao `generate_subtasks()` |
| `outputs` | Ground truth do lab | Disponível ao evaluator como `reference_outputs` |

O subset `quick` produz exactamente 4 exemplos (sqli, xss, auth, xxe).

### `_make_generator_target(skills_dir)` — closure do target

```python
def _make_generator_target(skills_dir: str):
    from pentest.agents.generator import generate_subtasks
    from pentest.models.recon import BackendProfile

    def target(inputs: dict) -> dict:
        profile = BackendProfile(
            primary_target=inputs["lab_url"],
            backend_type=inputs.get("expected_backend_type", "custom_api"),
            confidence="medium",
            scan_path=[f"fase-{inputs['fase_phase']}"],
        )
        subtasks = generate_subtasks(
            input=inputs["expected_vulnerability"],
            backend_profile=profile,
            skills_dir=skills_dir,
        )
        return {
            "subtasks": [s.model_dump() for s in subtasks],
            "count": len(subtasks),
        }

    return target
```

O target é uma closure que captura `skills_dir`. LangSmith exige que `target` seja callable `(inputs: dict) -> dict` — a closure adapta a interface do `generate_subtasks` para esse contrato.

**`scan_path` derivado de `fase_phase`:** o dataset fornece `fase_phase` como inteiro (ex: `3`). O target constrói `["fase-3"]` para passar ao `BackendProfile.scan_path`, que por sua vez alimenta o `load_fase_index()`.

### `_run_local()` — execução sem LangSmith

```python
def _run_local(target, examples, evaluators, runs) -> list[dict]:
    results = []
    for run_i in range(runs):
        for ex in examples:
            t0 = time.perf_counter()
            error = None
            output: dict = {}

            try:
                output = target(ex["inputs"])
            except Exception as e:
                error = str(e)

            scores = {}
            for evaluator in evaluators:
                try:
                    result = evaluator(output, ex.get("outputs", {}))
                    scores[result["key"]] = result["score"]
                except Exception as e:
                    scores["evaluator_error"] = 0.0

            results.append({
                "lab_id": lab_id, "run": run_i + 1,
                "output": output, "error": error,
                "scores": scores, "elapsed_s": round(elapsed, 2),
            })
    return results
```

O runner nunca propaga excepções do target — captura-as e regista `error` no resultado. Isto garante que um lab com falha não aborta os restantes.

### `_run_with_langsmith()` — upload para LangSmith

```python
def _run_with_langsmith(target, examples, evaluators, runs, agent, subset):
    client = Client()
    dataset_name = f"portswigger-mvp-{subset}"
    experiment_prefix = f"generator-eval-{subset}"

    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(dataset_name=dataset_name, ...)
        client.create_examples(
            inputs=[ex["inputs"] for ex in examples],
            outputs=[ex.get("outputs", {}) for ex in examples],
            dataset_id=dataset.id,
        )

    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix=experiment_prefix,
        metadata={"agent": agent, "subset": subset},
        num_repetitions=runs,
    )
```

**Porque criar o dataset no LangSmith em vez de passar os exemplos directamente?**

`client.evaluate()` espera `data` como nome/ID de um dataset LangSmith (ou iterável de `Example` objects). Passar uma lista de dicts brutos causa `AttributeError: 'dict' object has no attribute 'dataset_id'`. A solução é criar o dataset na primeira execução (idempotente via `has_dataset`) e reutilizá-lo nas seguintes.

O dataset criado tem nome fixo `portswigger-mvp-{subset}` (ex: `portswigger-mvp-quick`) — fica persistido no LangSmith e acumulam-se experimentos ao longo do tempo, permitindo comparações de regressão.

### `_print_metrics()` — métricas locais

```python
for key in sorted(score_keys):
    values = [r["scores"].get(key, 0.0) for r in results]
    avg = sum(values) / len(values)
    passed = sum(1 for v in values if v >= 1.0)
    print(f"  {key}:")
    print(f"    avg score : {avg:.3f}")
    print(f"    pass rate : {passed}/{len(values)} ...")

final_score = mean(per_run_mean_scores)
```

O `final_score` é a média dos scores médios por run — se houver vários evaluators, cada um contribui com peso igual para o score final. Passes são contados como `score >= 1.0`.

---

## 4) `tests/evals/evaluators/subtask_plan.py` — `subtask_plan_valid`

```python
def subtask_plan_valid(outputs: dict, reference_outputs: dict | None = None) -> dict:
```

| Campo retornado | Tipo | Descrição |
|---|---|---|
| `key` | `str` | Nome do evaluator (`"subtask_plan_valid"`) |
| `score` | `float` 0-1 | Pontuação: 1.0 = válido, 0.0 = inválido, parcial = campos em falta |
| `comment` | `str` | Descrição legível do resultado |

### Regras de avaliação (em ordem)

```
outputs.get("subtasks")
        │
        ▼
    lista vazia?          → score=0.0
        │
        ▼
    len > 15?             → score=0.0
        │
        ▼
    cada item é dict?     → score=0.0 se não
        │
        ▼
    title + description   → score parcial se algum estiver em branco
    não estão em branco?
        │
        ▼
    score=1.0
```

**Score parcial:** `1.0 - (campos_em_falta / (n_subtasks × 2))`. Com 3 subtasks e 1 campo em falta: `1.0 - 1/6 ≈ 0.83`.

**`reference_outputs` não é usado.** Este evaluator é puramente estrutural — não compara o conteúdo do plano com o ground truth do lab. A comparação semântica (ex: o plano menciona a vulnerabilidade esperada?) é responsabilidade de evaluators futuros (US-048).

---

## 5) `tests/evals/test_run_agent_eval.py` — Testes

### Estrutura de testes

| Classe | Cobertura |
|---|---|
| `TestHelp` | `--help` expõe as 4 flags obrigatórias via subprocess |
| `TestArgumentParsing` | Flags correctas; defaults; rejeição de agentes desconhecidos |
| `TestLoadExamples` | 4 exemplos no subset `quick`; campos obrigatórios; URL PortSwigger; exit(1) em subset inválido |
| `TestRunLocal` | Score 1.0 com stub válido; 2 runs = 2×N resultados; captura de excepção do target |
| `TestPrintMetrics` | `Final score`, nome do evaluator, `avg score`, `pass rate`, valor `0.750` |
| `TestRunnerE2E` | CLI subprocess real com LLM (marcado `@pytest.mark.e2e`) |

### Stub de subtarefas

```python
_STUB_SUBTASKS = [
    {
        "title": "Enumerate login endpoint parameters",
        "description": "Run ffuf against the login form...",
        "fase": "fase-3",
    },
    ...  # 3 subtasks no total
]
_STUB_OUTPUT = {"subtasks": _STUB_SUBTASKS, "count": 3}
```

O stub representa um plano realista para SQL injection, com `title`, `description`, e `fase` preenchidos. É usado pelos testes de `_run_local` e `_print_metrics` para verificar score 1.0 sem chamar o LLM.

### Teste de falha do target

```python
def _target_fail(inputs: dict) -> dict:
    raise RuntimeError("OPENAI_API_KEY not set")

def test_run_local_handles_target_exception(self):
    results = _run_local(_target_fail, examples, [subtask_plan_valid], runs=1)
    assert results[0]["error"] == "OPENAI_API_KEY not set"
    assert results[0]["output"] == {}
    assert results[0]["scores"].get("subtask_plan_valid") == 0.0
```

Verifica o caminho de falha completo: target lança excepção → `output={}` → evaluator recebe dict vazio → `score=0.0` (sem subtasks). O runner não deve propagar a excepção.

### Teste E2E

```python
@pytest.mark.e2e
class TestRunnerE2E:
    def test_runner_executes_generator_quick_no_upload(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--agent", "generator",
             "--subset", "quick", "--no-upload"],
            ...
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        assert result.returncode == 0
        assert "Final score" in result.stdout
        assert "sqli-login-bypass" in result.stdout
```

Corre o runner como subprocess real com o Generator completo. Requer `OPENAI_API_KEY`. Marcado `@pytest.mark.e2e` para ser excluído de CI standard e correr apenas via `workflow_dispatch`.

O `PYTHONPATH=REPO_ROOT` passado ao subprocess replica o `sys.path.insert` do script para o processo filho.

---

## Exemplo de Execução

```bash
# Modo local (sem LangSmith)
python tests/evals/run_agent_eval.py --agent generator --subset quick --no-upload

# Modo LangSmith (cria dataset na primeira execução)
python tests/evals/run_agent_eval.py --agent generator --subset quick

# Com modelo Claude
GENERATOR_MODEL=anthropic:claude-sonnet-4-6 \
python tests/evals/run_agent_eval.py --agent generator --subset quick
```

**Saída local esperada:**

```
Loaded 4 example(s) from subset 'quick'

Running 4 evaluation(s) (4 example(s) × 1 run(s))...

  [run 1/1] sqli-login-bypass ... ok (8.2s, 5 subtasks)
  [run 1/1] xss-reflected-html-nothing-encoded ... ok (7.1s, 4 subtasks)
  ...

============================================================
  Agent Evaluation Results
  Agent: generator  |  Subset: quick  |  Runs: 4
============================================================

  subtask_plan_valid:
    avg score : 1.000
    pass rate : 4/4 (100%)

  Success rate : 100% (4/4)
  Final score  : 1.000
```

---

## Padrao de Implementacao

O runner segue o padrão LangSmith de avaliação em dois modos:

```
              ┌─────────────────┐
              │  run_agent_eval │
              └────────┬────────┘
                       │
           ┌───────────▼────────────┐
           │   --no-upload?         │
           └───┬───────────────┬───┘
               │ sim           │ não
               ▼               ▼
        _run_local()    _run_with_langsmith()
               │               │
               │        cria/reutiliza
               │        dataset LangSmith
               │               │
               └───────┬───────┘
                       │
              avalia com evaluators
                       │
              imprime métricas / dashboard LangSmith
```

Este padrão é extensível: novos agentes adicionam um `_make_<agent>_target()` e uma entrada em `SUPPORTED_AGENTS`.

---

## Related Notes

- [Docs Home](../../README.md)
- [[Epics/Agent Evaluation/README|Agent Evaluation Hub]]
- [[Epics/Agent Evaluation/US-045-PORTSWIGGER-MVP-DATASET-EXPLAINED|US-045 PortSwigger MVP Dataset]]
- [[Epics/Generator agent/US-037-BASE-GRAPH-EXPLAINED|US-037 Base Graph]]
- [[Epics/Generator agent/US-043-GENERATOR-PROMPTS-EXPLAINED|US-043 Generator Prompts]]
- [[LANGSMITH-EVALS-RESEARCH]]
