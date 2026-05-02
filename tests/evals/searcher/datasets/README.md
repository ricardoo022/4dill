# Searcher Dataset

This folder contains evaluation datasets for the Searcher agent in the LusitAI architecture.

## Files
- `searcher.json`: The core ground truth dataset with 12 distinct pentest research scenarios.

## Schema

Each scenario in the JSON dataset follows this schema:

- `inputs.question` (string): The research query presented to the agent.
- `inputs.context` (string, optional): Extra context for the query.
- `reference_outputs.required_facts` (list of strings): Facts that must be explicitly present in the final output. These should be short, verifiable, and word-independent.
- `reference_outputs.acceptable_sources` (list of strings): A flexible allowlist of domains or URLs where the agent should draw information from.
- `reference_outputs.expected_tools` (list of strings): Tools that the agent is expected to use (e.g., `web_search`, `browser`, `search_answer`). This acts as a subset rather than a strict sequence.
- `reference_outputs.disallowed_behaviors` (list of strings): Explicit negative constraints (e.g., "Inventing internal policies").
- `metadata.category` (string): One of `cve`, `version`, `technique`, `tool`, `memory`, or `browser_followup`.
- `metadata.difficulty` (string): `easy`, `medium`, or `hard`.

## Adding New Scenarios

When extending this dataset:
1. Ensure the scenario represents a realistic pentest research query.
2. Formulate `required_facts` so they are easy to evaluate programmatically via LLM.
3. For internal knowledge base scenarios, categorize as `memory` and mandate `search_answer` in `expected_tools`.
4. For deep-dive analyses requiring full advisories, categorize as `browser_followup` and mandate `browser`.

## Validating Ground Truth

To validate changes:
1. Run the test suite: `pytest tests/evals/searcher/test_dataset.py -v`.
2. Ensure the JSON remains structurally valid and constraints (like the minimum counts for specific categories) hold.
