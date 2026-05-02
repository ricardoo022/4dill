"""CLI runner for agent evaluation against the PortSwigger MVP dataset.

Usage:
    python tests/evals/run_agent_eval.py --agent generator --subset quick --no-upload
    python tests/evals/run_agent_eval.py --agent generator --subset quick
    python tests/evals/run_agent_eval.py --help

Environment variables:
    ANTHROPIC_API_KEY   — required for Generator evaluation
    LANGSMITH_API_KEY   — required when uploading results (omit --no-upload)
    GENERATOR_MODEL     — model to use, provider:model format or bare name (default: gpt-4.1-mini)
                          examples: openai:gpt-4o, anthropic:claude-sonnet-4-6, gpt-4.1-mini
    SKILLS_DIR          — path to skills root (default: lusitai-internal-scan/.claude/skills)
"""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASET_PATH = Path(__file__).parent / "datasets" / "portswigger_mvp.json"
DEFAULT_SKILLS_DIR = REPO_ROOT / "lusitai-internal-scan" / ".claude" / "skills"

SUPPORTED_AGENTS = ("generator",)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_agent_eval.py",
        description="Run agent evaluation against the PortSwigger MVP dataset.",
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=SUPPORTED_AGENTS,
        help="Agent to evaluate (currently: generator)",
    )
    parser.add_argument(
        "--subset",
        default="quick",
        help="Dataset subset to evaluate against (default: quick)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Run locally without uploading results to LangSmith",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="N",
        help="Number of evaluation runs per example (default: 1)",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(DEFAULT_SKILLS_DIR),
        metavar="PATH",
        help=f"Root directory with scan-fase-* skill folders (default: {DEFAULT_SKILLS_DIR})",
    )
    return parser


def _load_examples(subset: str) -> list[dict]:
    """Load lab examples for a given subset from the MVP dataset."""
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
        examples.append(
            {
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
            }
        )
    return examples


def _make_generator_target(skills_dir: str):
    """Return a target function that calls the Generator agent."""
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


def _run_local(
    target,
    examples: list[dict],
    evaluators: list,
    runs: int,
) -> list[dict]:
    """Run evaluation locally without LangSmith, returning a list of result records."""
    results = []
    total = len(examples) * runs

    print(f"\nRunning {total} evaluation(s) ({len(examples)} example(s) × {runs} run(s))...\n")

    for run_i in range(runs):
        for ex in examples:
            lab_id = ex["inputs"]["lab_id"]
            label = f"[run {run_i + 1}/{runs}] {lab_id}"
            print(f"  {label} ... ", end="", flush=True)

            t0 = time.perf_counter()
            error = None
            output: dict = {}

            try:
                output = target(ex["inputs"])
                elapsed = time.perf_counter() - t0
                print(f"ok ({elapsed:.1f}s, {output.get('count', 0)} subtasks)")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                error = str(e)
                print(f"ERROR ({elapsed:.1f}s): {error}")

            scores = {}
            for evaluator in evaluators:
                try:
                    result = evaluator(output, ex.get("outputs", {}))
                    scores[result["key"]] = result["score"]
                except Exception as e:
                    scores["evaluator_error"] = 0.0
                    print(f"    [evaluator error] {e}", file=sys.stderr)

            results.append(
                {
                    "lab_id": lab_id,
                    "run": run_i + 1,
                    "output": output,
                    "error": error,
                    "scores": scores,
                    "elapsed_s": round(elapsed, 2),
                }
            )

    return results


def _print_metrics(results: list[dict], agent: str, subset: str) -> None:
    """Print aggregated metrics and final score."""
    print(f"\n{'=' * 60}")
    print("  Agent Evaluation Results")
    print(f"  Agent: {agent}  |  Subset: {subset}  |  Runs: {len(results)}")
    print(f"{'=' * 60}\n")

    # Collect all score keys
    score_keys: set[str] = set()
    for r in results:
        score_keys.update(r["scores"].keys())

    for key in sorted(score_keys):
        values = [r["scores"].get(key, 0.0) for r in results]
        avg = sum(values) / len(values) if values else 0.0
        passed = sum(1 for v in values if v >= 1.0)
        print(f"  {key}:")
        print(f"    avg score : {avg:.3f}")
        print(f"    pass rate : {passed}/{len(values)} ({100 * passed / len(values):.0f}%)")

    # Overall score = mean of all evaluator averages
    if score_keys:
        per_run_scores = []
        for r in results:
            if r["scores"]:
                per_run_scores.append(sum(r["scores"].values()) / len(r["scores"]))
        final_score = sum(per_run_scores) / len(per_run_scores) if per_run_scores else 0.0
    else:
        final_score = 0.0

    error_count = sum(1 for r in results if r["error"])
    success_rate = (len(results) - error_count) / len(results) if results else 0.0

    print(f"\n  Success rate : {success_rate:.0%} ({len(results) - error_count}/{len(results)})")
    print(f"  Final score  : {final_score:.3f}\n")

    if error_count:
        print(f"  {error_count} run(s) failed — errors logged above\n")


def _run_with_langsmith(
    target,
    examples: list[dict],
    evaluators: list,
    runs: int,
    agent: str,
    subset: str,
) -> None:
    """Run evaluation via LangSmith and upload results."""
    from langsmith import Client

    client = Client()
    dataset_name = f"portswigger-mvp-{subset}"
    experiment_prefix = f"generator-eval-{subset}"

    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description=f"PortSwigger MVP {subset} eval dataset",
        )
        client.create_examples(
            inputs=[ex["inputs"] for ex in examples],
            outputs=[ex.get("outputs", {}) for ex in examples],
            dataset_id=dataset.id,
        )
        print(f"Created LangSmith dataset '{dataset_name}' with {len(examples)} examples")
    else:
        print(f"Using existing LangSmith dataset '{dataset_name}'")

    print(f"\nRunning experiment: prefix='{experiment_prefix}'\n")

    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix=experiment_prefix,
        metadata={"agent": agent, "subset": subset},
        num_repetitions=runs,
    )

    # Print summary from LangSmith results
    print(f"\n{'=' * 60}")
    print("  LangSmith Evaluation Results")
    print(f"  Agent: {agent}  |  Subset: {subset}")
    print(f"{'=' * 60}\n")

    try:
        for result in results:
            lab_id = result.get("example", {}).get("inputs", {}).get("lab_id", "?")
            eval_results = result.get("evaluation_results", {}).get("results", [])
            scores = {r.key: r.score for r in eval_results if hasattr(r, "key")}
            print(f"  {lab_id}: {scores}")
    except Exception:
        print("  (results available in LangSmith dashboard)")

    print()


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Validate skills dir
    skills_dir = args.skills_dir
    if not Path(skills_dir).exists():
        print(
            f"Warning: skills_dir not found: {skills_dir}\n"
            "  Set --skills-dir or ensure lusitai-internal-scan submodule is initialised.",
            file=sys.stderr,
        )

    # Load dataset
    examples = _load_examples(args.subset)
    print(f"Loaded {len(examples)} example(s) from subset '{args.subset}'")

    # Build target
    if args.agent == "generator":
        target = _make_generator_target(skills_dir)
    else:
        print(f"Error: unsupported agent '{args.agent}'", file=sys.stderr)
        sys.exit(1)

    # Load evaluators
    from tests.evals.evaluators import subtask_plan_valid

    evaluators = [subtask_plan_valid]

    # Run
    if args.no_upload:
        results = _run_local(target, examples, evaluators, runs=args.runs)
        _print_metrics(results, agent=args.agent, subset=args.subset)
    else:
        _run_with_langsmith(
            target,
            examples,
            evaluators,
            runs=args.runs,
            agent=args.agent,
            subset=args.subset,
        )


if __name__ == "__main__":
    main()
