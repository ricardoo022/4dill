"""CLI runner for Searcher agent evaluation.

Usage:
    python tests/evals/searcher/run_searcher_eval.py --no-upload
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Add repo root and src to sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pentest.agents.searcher import perform_search  # noqa: E402
from pentest.providers.factory import create_chat_model  # noqa: E402

load_dotenv()

DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "searcher.json"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_searcher_eval.py",
        description="Run Searcher agent evaluation.",
    )
    parser.add_argument(
        "--model",
        help="LLM model to use for the Searcher agent.",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help=f"Path to the dataset JSON file (default: {DEFAULT_DATASET_PATH})",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=2,
        help="Evaluation level: 1=final answer, 2=fixtures, 3=controlled E2E (default: 2)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Run locally without uploading results to LangSmith",
    )
    parser.add_argument(
        "--judge-model",
        help="Model to use for judging (default from EVAL_JUDGE_MODEL env)",
    )
    return parser


async def run_eval(args: argparse.Namespace) -> None:
    """Run the evaluation."""
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        # Create a placeholder dataset if it doesn't exist
        if args.no_upload:
            print("Creating placeholder dataset for local run...")
            dataset_path.parent.mkdir(parents=True, exist_ok=True)
            placeholder = {
                "scenarios": [
                    {
                        "inputs": {"question": "What is the latest CVE for nginx?"},
                        "reference_outputs": {"required_facts": ["CVE-2024-"]},
                    }
                ]
            }
            with open(dataset_path, "w", encoding="utf-8") as f:
                json.dump(placeholder, f, indent=2)
        else:
            sys.exit(1)

    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    scenarios = dataset.get("scenarios", [])
    print(f"Loaded {len(scenarios)} scenarios from {dataset_path}")

    llm = create_chat_model(agent_name="searcher")
    if args.model:
        # In a real scenario, we might want to re-initialize the LLM with the specific model
        pass

    results = []
    for scenario in scenarios:
        question = scenario["inputs"]["question"]
        print(f"Evaluating: {question} ... ", end="", flush=True)

        t0 = time.perf_counter()
        try:
            # For now, we just call perform_search
            # In level 2, we might want to use fixtures/recordings
            result = await perform_search(
                question=question,
                llm=llm,
            )
            elapsed = time.perf_counter() - t0
            print(f"DONE ({elapsed:.1f}s)")
            results.append({"scenario": scenario, "output": result, "status": "success"})
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"FAILED ({elapsed:.1f}s): {e}")
            results.append({"scenario": scenario, "error": str(e), "status": "failed"})

    # Print summary
    successes = sum(1 for r in results if r["status"] == "success")
    print(f"\nSummary: {successes}/{len(results)} successful runs.")


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run_eval(args))


if __name__ == "__main__":
    main()
