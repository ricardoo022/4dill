---
tags: [evaluation]
---

# LangSmith Evaluations Research (2025)

**Research Date:** April 2025
**SDK Version:** LangSmith Python SDK v0.2+
**Status:** Current production patterns

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Evaluator Types](#evaluator-types)
3. [Creating Custom Evaluators](#creating-custom-evaluators)
4. [Running Evaluations](#running-evaluations)
5. [Scoring System](#scoring-system)
6. [Agent-Specific Evaluation](#agent-specific-evaluation)
7. [Best Practices for LLM Agents](#best-practices-for-llm-agents)
8. [Code Examples](#code-examples)

---

## Core Concepts

LangSmith evaluations measure quality throughout the application lifecycle using four foundational concepts:

### Datasets

Collections of test cases for offline evaluation. Each dataset contains multiple **examples** that define what "good" looks like for your application.

- **Versioning**: LangSmith creates automatic versions on every edit/deletion for audit trail
- **Tagging**: Mark versions that matter for evaluation
- **Sources**: Manually curated test cases, historical production traces, or synthetic data
- **Example composition**: Each example includes:
  - **Inputs**: Variables passed to your application
  - **Reference outputs** (optional): Expected results used only by evaluators
  - **Metadata** (optional): Tags and additional context

### Examples

Individual test cases within a dataset. Examples are the atomic unit of evaluation—one example represents one test scenario.

### Evaluators

Functions that score application performance. They adapt based on evaluation type:

- **Offline evaluators**: Receive both examples (with reference outputs) and actual application outputs
- **Online evaluators**: Receive only production runs (no reference answers available)

Evaluators return **feedback** containing:
- **key**: Metric name (string identifier)
- **score**: Boolean, float (0-1), or categorical value
- **metadata** (optional): Additional context (reasoning, evidence)

### Experiments

Results from testing a specific application version against a dataset. Each experiment captures:
- Outputs from every example
- Evaluator scores
- Execution traces (LLM calls, tool invocations, latencies)
- Per-example metrics and aggregates

**Comparison**: Compare experiments side-by-side for benchmarking, unit tests, regression tests, or backtesting across different prompt versions, models, or agent systems.

---

## Evaluator Types

LangSmith supports four primary evaluator patterns:

### 1. **LLM-as-Judge Evaluators**

Use Claude, GPT-4, or other LLMs to score applications against custom rubrics. Ideal for nuanced, qualitative assessment.

```python
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

evaluator = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT,
    model="openai:gpt-4-turbo",
    feedback_key="correctness"
)
```

**Use cases:**
- Correctness evaluation against ground truth
- Tone/style assessment
- Relevance scoring
- Hallucination detection

**Signature:**
```python
def llm_judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    # Returns: {"correctness": 0.8, "reasoning": "..."}
    pass
```

### 2. **Heuristic/Code-Based Evaluators**

Deterministic, rule-based functions for simple checks. Fast and reproducible.

```python
def is_valid_output(outputs: dict) -> bool:
    """Check if output is not empty and is a string."""
    answer = outputs.get("answer", "")
    return isinstance(answer, str) and len(answer) > 0

def is_code_compilable(outputs: dict) -> dict:
    """Check if generated code compiles."""
    try:
        compile(outputs["code"], "<string>", "exec")
        return {"code_compiles": True}
    except SyntaxError:
        return {"code_compiles": False, "error": "Invalid syntax"}
```

**Use cases:**
- Format validation
- Code compilation checks
- Pattern matching
- Threshold-based scoring

### 3. **Trajectory Match Evaluators**

Compare actual agent execution against expected or reference trajectories. Four modes:

```python
from agentevals import create_trajectory_match_evaluator

# Strict: Identical sequence required
evaluator_strict = create_trajectory_match_evaluator(
    trajectory_match_mode="strict"
)

# Unordered: Same tools, any order
evaluator_unordered = create_trajectory_match_evaluator(
    trajectory_match_mode="unordered"
)

# Superset: Key tools must be called (extras OK)
evaluator_superset = create_trajectory_match_evaluator(
    trajectory_match_mode="superset"
)

# Subset: No extra calls allowed
evaluator_subset = create_trajectory_match_evaluator(
    trajectory_match_mode="subset"
)
```

**Modes explained:**
- **Strict**: "check policy before authorization" workflows where order matters
- **Unordered**: Multiple independent tool calls where order doesn't matter
- **Superset**: "must call search AND retrieval, extras OK" patterns
- **Subset**: "no unnecessary tool calls allowed" constraints

### 4. **Human Evaluation**

Manual annotation through LangSmith UI. Combines with automated evaluators for bootstrapping and refinement.

**Workflow:**
1. Run automated evaluators (LLM-as-judge, heuristic)
2. Sample interesting/problematic runs into dataset
3. Human reviewers annotate via annotation queues
4. Refine automated evaluators with human feedback

---

## Creating Custom Evaluators

### Python SDK API (v0.2+ Simplified)

In SDK v0.2+, evaluators accept three dictionaries directly:

```python
def my_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Simple evaluator returning a primitive."""
    prediction = outputs.get("answer")
    expected = reference_outputs.get("answer")

    # Return primitives directly: bool, int, float, str
    return {"exact_match": prediction == expected}
```

**Key simplifications in v0.2:**
- Primitives (float, int, bool, str) can be returned directly
- No need to wrap in `EvaluationResult` for simple cases
- Cleaner argument names: `inputs`, `outputs`, `reference_outputs`

### Advanced: With Run and Example Objects

For accessing intermediate steps and metadata:

```python
from langsmith.evaluation import EvaluationResult, run_evaluator
from langsmith.schemas import Example, Run

@run_evaluator
def check_agent_uncertainty(run: Run, example: Example):
    """Check if agent admits uncertainty appropriately."""
    agent_response = run.outputs["output"]

    contains_idk = (
        "don't know" in agent_response.lower() or
        "not sure" in agent_response.lower()
    )

    return EvaluationResult(
        key="appropriately_uncertain",
        score=1 if contains_idk else 0,
    )
```

**Run object properties:**
- `run.inputs`: User inputs to the agent
- `run.outputs`: Agent outputs
- `run.intermediate_steps`: List of tool calls and responses
- `run.error`: Any error that occurred
- `run.execution_time`: Runtime in seconds

**Example object properties:**
- `example.inputs`: Reference inputs
- `example.outputs`: Reference outputs (ground truth)
- `example.metadata`: Tags, annotations, custom data

### Return Format Specification

Evaluators can return:

**Simple (v0.2+):**
```python
return 0.85  # float
return True  # bool
return "pass"  # str
return {"exact_match": True}  # dict with primitive values
```

**Detailed (with metadata):**
```python
return {
    "key": "correctness",
    "score": 0.75,
    "comment": "Mostly correct but missing nuance",
    "metadata": {"model_used": "gpt-4"}
}
```

**Multiple scores:**
```python
return {
    "results": [
        {"key": "precision", "score": 0.8},
        {"key": "recall", "score": 0.9},
        {"key": "f1", "score": 0.85}
    ]
}
```

---

## Running Evaluations

### Basic Synchronous Evaluation

```python
from langsmith import Client

client = Client()

def target_function(inputs: dict) -> dict:
    """Your application to evaluate."""
    question = inputs["question"]
    answer = expensive_llm_call(question)
    return {"answer": answer}

def correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    return {"correct": outputs["answer"] == reference_outputs["answer"]}

# Run evaluation
experiment_results = client.evaluate(
    target=target_function,
    data="My Dataset",  # Dataset name or list of dicts
    evaluators=[correctness_evaluator],
    experiment_prefix="my-experiment",
    max_concurrency=4,
    num_repetitions=1
)

# Results accessible via experiment_results
for result in experiment_results:
    print(f"Feedback: {result.feedback}")
```

**Parameters:**
- `target`: Function or LangChain object to evaluate
- `data`: Dataset name, list, or async generator
- `evaluators`: List of evaluator functions
- `summary_evaluators`: Optional summary-level evaluators (aggregate scores)
- `experiment_prefix`: Namespace for experiment names
- `max_concurrency`: Parallel execution (0 = no parallel)
- `num_repetitions`: Run each example N times

### Async Evaluation

```python
from langsmith.evaluation import aevaluate
import asyncio

async def async_target(inputs: dict) -> dict:
    """Your async application."""
    answer = await async_llm_call(inputs["question"])
    return {"answer": answer}

async def main():
    results = await aevaluate(
        target=async_target,
        data="My Dataset",
        evaluators=[correctness_evaluator],
        max_concurrency=8
    )
    return results

results = asyncio.run(main())
```

### Evaluating Existing Runs

Re-evaluate runs you already executed (adds new evaluators without re-running target):

```python
experiment_results = client.evaluate_existing(
    project_name="my-project",
    evaluators=[new_evaluator_1, new_evaluator_2],
    experiment_prefix="retry-evals"
)
```

### Comparative Evaluation

Run two versions against same dataset:

```python
results = client.evaluate_comparative(
    experiments=["experiment-1-id", "experiment-2-id"],
    evaluators=[new_evaluator],
    comparison_name="version-comparison"
)
```

### Local Testing (Upload=False)

Run evaluations locally without storing in LangSmith (beta):

```python
results = client.evaluate(
    target=target_function,
    data=my_dataset,
    evaluators=[evaluators],
    upload_results=False  # Skip uploading to cloud
)
```

---

## Scoring System

### Score Types

LangSmith supports three score categories:

#### 1. **Binary Scores**
Default evaluator type. Returns `True` / `False`.

```python
def is_correct(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["answer"] == reference_outputs["answer"]
```

#### 2. **Continuous Scores**
Float values between 0 and 1.

```python
from sklearn.metrics import rouge_score

def semantic_similarity(outputs: dict, reference_outputs: dict) -> float:
    score = rouge_score(
        outputs["answer"],
        reference_outputs["answer"]
    )
    return float(score)
```

#### 3. **Categorical Scores**
Discrete choices with numeric values.

```python
def quality_rating(outputs: dict) -> str:
    # Returns one of: "poor", "fair", "good", "excellent"
    rating_map = {"poor": 1, "fair": 2, "good": 3, "excellent": 4}
    return rating_map.get(outputs.get("rating"), 0)
```

### Feedback Structure

All feedback follows this structure:

```python
{
    "key": "metric_name",           # Required
    "score": 0.85,                  # Required (bool, int, float, or str)
    "comment": "Explanation",       # Optional string
    "metadata": {                   # Optional
        "model": "gpt-4",
        "tokens_used": 450
    }
}
```

### Aggregation

LangSmith automatically aggregates:
- **Mean score** per metric
- **Pass rate** (% > threshold)
- **Distribution** of scores
- **Comparisons** across experiments

---

## Agent-Specific Evaluation

### 1. **Trajectory Evaluators**

Evaluate the full sequence of tool calls and reasoning steps.

```python
from agentevals import create_trajectory_llm_as_judge, TRAJECTORY_ACCURACY_PROMPT

evaluator = create_trajectory_llm_as_judge(
    model="openai:gpt-4-turbo",
    prompt=TRAJECTORY_ACCURACY_PROMPT
)

# Run on agent output
feedback = evaluator(
    outputs=agent_messages,
    reference_outputs=expected_trajectory
)
```

**What gets evaluated:**
- Sequence of tool calls
- Reasoning between steps
- Appropriateness of tool selection
- Completeness of task execution

### 2. **Tool Call Validation**

Inspect intermediate steps and validate tool invocations:

```python
@run_evaluator
def tool_call_validity(run: Run, example: Example):
    """Check if tool calls are valid and relevant."""
    intermediate_steps = run.intermediate_steps

    score = 0
    for tool_name, tool_input in intermediate_steps:
        # Validate tool name exists
        if tool_name not in VALID_TOOLS:
            score -= 1
        # Validate input schema
        elif not validate_input_schema(tool_name, tool_input):
            score -= 1

    return EvaluationResult(
        key="tool_validity",
        score=max(0, score),
    )
```

**Accessible via `run.intermediate_steps`:**
- List of tuples: `(tool_name, tool_input, tool_output)`
- Captures entire decision pathway

### 3. **Multi-Turn Agent Evaluation**

Evaluate conversational agents across multiple turns:

```python
from openevals.simulators import run_multiturn_simulation, create_llm_simulated_user

def app(message: str, *, thread_id: str) -> str:
    """Your multi-turn agent."""
    # Maintain conversation history by thread_id
    history = load_conversation_history(thread_id)
    response = your_agent(message, history)
    save_conversation_history(thread_id, history + [message, response])
    return response

user = create_llm_simulated_user(
    system="You are a frustrated customer seeking a refund",
    model="openai:gpt-4-turbo"
)

result = run_multiturn_simulation(
    app=app,
    user=user,
    max_turns=5
)
```

**Trajectory evaluators can then assess:**
- Goal accomplishment across full conversation
- Handling of multi-turn context
- Consistency of persona
- Politeness and professionalism

### 4. **Step-by-Step Evaluation**

Run agent for N steps and evaluate intermediate decisions:

```python
@run_evaluator
def next_tool_correctness(run: Run, example: Example):
    """Score the next tool called by the agent."""
    expected_next_tool = example.outputs["expected_next_tool"]
    actual_next_tool = run.intermediate_steps[-1][0] if run.intermediate_steps else None

    return EvaluationResult(
        key="next_tool_correct",
        score=1 if actual_next_tool == expected_next_tool else 0
    )
```

**Benefits:**
- Early regression detection
- Token conservation
- Targeted debugging
- Lower latency feedback loop

---

## Best Practices for LLM Agents

### 1. **Tailor Success Criteria Per Example**

Don't apply identical evaluators to every datapoint:

```python
# Bad: Same evaluator for all examples
evaluators = [generic_correctness]

# Good: Custom per-example logic
@run_evaluator
def example_specific_eval(run: Run, example: Example):
    expected_keys = example.metadata.get("expected_outputs", [])
    actual_keys = set(run.outputs.keys())

    return EvaluationResult(
        key="output_keys_match",
        score=1 if all(k in actual_keys for k in expected_keys) else 0
    )
```

### 2. **Use Multi-Level Evaluation**

Combine different evaluators to capture different aspects:

```python
evaluators = [
    # Heuristic checks (fast)
    output_not_empty,

    # Trajectory validation (medium)
    tool_sequence_valid,

    # Semantic evaluation (slow, use sparingly)
    llm_judge_correctness
]
```

### 3. **Maintain Reproducibility**

Deep agents need clean environments for consistent results:

```python
import tempfile
import subprocess
from unittest.mock import patch
import vcr

@run_evaluator
def reproducible_agent_eval(run: Run, example: Example):
    # Use VCR for HTTP request mocking
    with vcr.VCR().use_cassette(f"cassettes/{example.id}.yaml"):
        # Run in isolated temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_agent_in_sandbox(tmpdir)

    return assess_result(result)
```

**Techniques:**
- Docker containers per evaluation
- VCR/pytest-mock for deterministic external calls
- Isolated filesystems (tempdir)
- Frozen time for date-dependent logic

### 4. **Handle Multi-Turn Conditionally**

For multi-step interactions, add conditional checks rather than hardcoding sequences:

```python
# Bad: Hardcoded sequence that breaks if agent deviates
user_inputs = ["find me a flight", "in economy", "departing tomorrow"]

# Good: Conditional logic that adapts
def adaptive_multiturn(agent):
    messages = []

    # Turn 1: Initial request
    response1 = agent("find me a flight")
    messages.append(response1)

    # Turn 2: Conditional on response
    if "clarify" in response1:
        response2 = agent("in economy class")
    else:
        response2 = agent("in economy, departing tomorrow")
    messages.append(response2)

    return messages
```

### 5. **Insights Agent for Pattern Discovery**

Use LangSmith's Insights Agent to auto-categorize agent behavior:

```python
# In LangSmith UI:
# 1. Capture production traces
# 2. Enable Insights Agent
# 3. Review discovered patterns:
#    - "Agent loops on same query"
#    - "Tool X returns empty results"
#    - "Incorrect confidence scores"

# Then sample interesting cases into dataset
dataset = client.create_dataset(
    name="agent-failure-patterns",
    description="Sampled from insights"
)
```

---

## Code Examples

### Complete Example 1: Q&A Evaluator

```python
from langsmith import Client, wrappers
from langchain.chat_models import ChatOpenAI
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

# Wrap LLM for tracing
llm = wrappers.wrap_openai(ChatOpenAI(model="gpt-4-turbo"))

def qa_target(inputs: dict) -> dict:
    """Question answering application."""
    question = inputs["question"]
    response = llm.invoke(
        [{"role": "user", "content": question}]
    )
    return {"answer": response.content}

def correctness_eval(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """LLM-as-judge correctness."""
    judge = create_llm_as_judge(
        prompt=CORRECTNESS_PROMPT,
        model="openai:gpt-4-turbo",
        feedback_key="correctness"
    )
    return judge(
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs
    )

def exact_match_eval(inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
    """Heuristic: Exact string match."""
    return outputs["answer"].strip() == reference_outputs["answer"].strip()

# Run evaluation
client = Client()
results = client.evaluate(
    target=qa_target,
    data="QA Dataset v1",
    evaluators=[exactness_eval, correctness_eval],
    experiment_prefix="qa-eval",
    max_concurrency=4
)

# Access results
for result in results:
    print(f"Feedback: {result.feedback}")
```

### Complete Example 2: Agent Trajectory Evaluation

```python
from langsmith import Client
from langsmith.schemas import Run, Example
from langsmith.evaluation import EvaluationResult, run_evaluator
from agentevals import create_trajectory_match_evaluator

def search_agent_target(inputs: dict) -> dict:
    """Agent with search and calculator tools."""
    query = inputs["query"]
    agent = ReActAgent(tools=[search_tool, calculator_tool])
    result = agent.run(query)

    return {
        "answer": result.output,
        "messages": result.messages
    }

@run_evaluator
def tool_sequence_correct(run: Run, example: Example):
    """Validate tool call sequence."""
    expected_sequence = example.outputs.get("expected_tools", [])
    actual_sequence = [
        step[0] for step in run.intermediate_steps
    ]

    # Check subset (all expected tools called, extras OK)
    match = all(t in actual_sequence for t in expected_sequence)

    return EvaluationResult(
        key="tool_sequence",
        score=1 if match else 0,
        comment=f"Expected {expected_sequence}, got {actual_sequence}"
    )

def trajectory_match_eval(outputs: dict, reference_outputs: dict) -> dict:
    """Trajectory match with LLM judge."""
    evaluator = create_trajectory_match_evaluator(
        trajectory_match_mode="superset"
    )
    return evaluator(
        outputs=outputs["messages"],
        reference_outputs=reference_outputs.get("messages", [])
    )

# Run
client = Client()
results = client.evaluate(
    target=search_agent_target,
    data="Agent Tasks v1",
    evaluators=[tool_sequence_correct, trajectory_match_eval],
    experiment_prefix="agent-trajectory"
)
```

### Complete Example 3: Multi-Turn Agent with Simulation

```python
from openevals.simulators import run_multiturn_simulation, create_llm_simulated_user
from langsmith import Client
from langsmith.evaluation import EvaluationResult, run_evaluator

class CustomerServiceAgent:
    def __init__(self):
        self.conversation_history = {}

    def chat(self, message: str, *, thread_id: str) -> str:
        """Multi-turn chat interface."""
        history = self.conversation_history.get(thread_id, [])

        response = llm.invoke(
            system="You are a helpful customer service agent",
            messages=history + [{"role": "user", "content": message}]
        )

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response.content})
        self.conversation_history[thread_id] = history

        return response.content

# Simulate user interactions
agent = CustomerServiceAgent()

user_angry = create_llm_simulated_user(
    system="You are an angry customer demanding a refund",
    model="openai:gpt-4-turbo"
)

user_confused = create_llm_simulated_user(
    system="You are confused about a feature and keep asking questions",
    model="openai:gpt-4-turbo"
)

# Run multi-turn simulation
trajectory_angry = run_multiturn_simulation(
    app=lambda msg: agent.chat(msg, thread_id="angry-customer"),
    user=user_angry,
    max_turns=5
)

@run_evaluator
def goal_accomplished(run: Run, example: Example):
    """Check if customer's goal was met."""
    expected_resolution = example.outputs["expected_resolution"]
    messages = run.outputs["messages"]

    # Simple heuristic: Check for resolution keywords
    final_response = messages[-1].content.lower()
    goal_met = any(
        keyword in final_response
        for keyword in expected_resolution.keywords
    )

    return EvaluationResult(
        key="goal_accomplished",
        score=1 if goal_met else 0
    )

# Evaluate trajectory
client = Client()
results = client.evaluate(
    target=lambda inputs: trajectory_angry,
    data="Customer Service Scenarios",
    evaluators=[goal_accomplished],
    experiment_prefix="multiturn-cs"
)
```

### Example 4: Custom Heuristic with Code-Based Checks

```python
from langsmith.evaluation import EvaluationResult, run_evaluator
from langsmith.schemas import Run, Example

@run_evaluator
def response_quality_checks(run: Run, example: Example):
    """Multi-check heuristic evaluator."""
    output = run.outputs.get("text", "")
    results = []

    # Check 1: Length
    if len(output) < 20:
        results.append({
            "key": "response_too_short",
            "score": 0,
            "comment": f"Only {len(output)} characters"
        })
    else:
        results.append({"key": "response_too_short", "score": 1})

    # Check 2: No insults
    insults = ["stupid", "idiot", "dumb"]
    has_insults = any(i in output.lower() for i in insults)
    results.append({
        "key": "no_insults",
        "score": 0 if has_insults else 1
    })

    # Check 3: Structured output
    import json
    try:
        if output.startswith("{"):
            json.loads(output)
            results.append({"key": "valid_json", "score": 1})
    except json.JSONDecodeError:
        results.append({"key": "valid_json", "score": 0})

    return {"results": results}
```

---

## References

**Official Documentation:**
- [LangSmith Evaluation Concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- [Evaluation Quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart)
- [Custom Code Evaluators](https://docs.langchain.com/langsmith/code-evaluator)
- [Trajectory Evaluations](https://docs.langchain.com/langsmith/trajectory-evals)
- [Multi-Turn Simulation](https://docs.langchain.com/langsmith/multi-turn-simulation)

**Recent Blog Posts:**
- [Easier Evaluations with SDK v0.2](https://blog.langchain.com/easier-evaluations-with-langsmith-sdk-v0-2/)
- [Insights Agent & Multi-Turn Evals](https://blog.langchain.com/insights-agent-multiturn-evals-langsmith/)
- [Evaluating Deep Agents: Our Learnings](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)

**Code Examples:**
- [LangSmith Cookbook: Evaluating Agents](https://github.com/langchain-ai/langsmith-cookbook/blob/main/testing-examples/agent_steps/evaluating_agents.ipynb)
- [LangSmith Cookbook: LangGraph Agent Eval](https://github.com/langchain-ai/langsmith-cookbook/blob/main/testing-examples/agent-evals-with-langgraph/langgraph_sql_agent_eval.ipynb)
- [Agent Evals GitHub](https://github.com/langchain-ai/agentevals)

**Related Packages:**
- `langsmith` — Core SDK
- `openevals` — Pre-built LLM-as-judge and heuristic evaluators
- `agentevals` — Agent trajectory evaluators

---

## Key Takeaways for Your Pentest Agent

1. **Trajectory evaluation** is essential: Score tool call sequences, not just final outputs
2. **Custom heuristics** for security: Validate tool calls match expected security patterns
3. **Multi-step scoring**: Evaluate intermediate reasoning, not just conclusions
4. **Reproducible environments**: Use Docker/VCR for deterministic agent evaluation
5. **Combine evaluators**: Mix fast heuristics with slow LLM judges for efficiency
6. **Reference trajectories**: Store expected agent workflows for trajectory matching
7. **Metadata tracking**: Log which model/config produced each evaluation for debugging

---

## Related Notes

- [[Epics/Agent Evaluation/README|Agent Evaluation]]
- [[EVAL-TARGETS]]
- [[USER-STORIES]]
- [[PROJECT-STRUCTURE]]
- [[AGENT-ARCHITECTURE]]
