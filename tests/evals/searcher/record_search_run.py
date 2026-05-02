"""Script to record a Searcher agent run for evaluation and dataset building.

Usage:
    python tests/evals/searcher/record_search_run.py --question "CVE-2024-1234 impact"
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

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


class TrajectoryCallbackHandler(AsyncCallbackHandler):
    """Callback handler to record agent trajectories (messages and tool calls)."""

    def __init__(self):
        self.tool_calls: list[dict[str, Any]] = []

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], **kwargs: Any) -> None:
        """Ignore chat model start."""
        pass

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        # tool_start provides name and input
        tool_name = serialized.get("name")
        self.tool_calls.append(
            {
                "name": tool_name,
                "input": input_str,
                "start_time": datetime.now().isoformat(),
            }
        )

    async def on_tool_end(self, output: str, **kwargs) -> None:
        # tool_end provides output. We match it to the last tool_start.
        if self.tool_calls:
            self.tool_calls[-1]["output"] = output
            self.tool_calls[-1]["end_time"] = datetime.now().isoformat()


def _serialize_message(msg: BaseMessage) -> dict[str, Any]:
    """Serialize a LangChain message to a dict."""
    data: dict[str, Any] = {
        "role": "unknown",
        "content": msg.content,
    }
    if hasattr(msg, "type"):
        data["role"] = msg.type

    if isinstance(msg, AIMessage) and msg.tool_calls:
        data["tool_calls"] = msg.tool_calls

    if isinstance(msg, ToolMessage):
        data["tool_call_id"] = msg.tool_call_id
        data["name"] = msg.name

    return data


async def record_run(
    question: str,
    output_path: Path | None = None,
    runs: int = 1,
    context: str = "",
    use_fixtures: bool = False,
) -> None:
    """Run the searcher and record the execution."""
    llm = create_chat_model(agent_name="searcher")

    for i in range(runs):
        print(f"Running iteration {i + 1}/{runs}...")

        start_time = datetime.now()
        run_id = str(uuid.uuid4())
        handler = TrajectoryCallbackHandler()

        try:
            from langchain_core.tracers.context import collect_runs

            with collect_runs() as cb:
                result = await perform_search(
                    question=question,
                    llm=llm,
                    execution_context=context,
                    callbacks=[handler],
                )
                run = cb.traced_runs[0] if cb.traced_runs else None

            end_time = datetime.now()

            record = {
                "run_id": run_id,
                "timestamp": start_time.isoformat(),
                "inputs": {
                    "question": question,
                    "context": context,
                },
                "output": result,
                "tool_calls": handler.tool_calls,
                "elapsed_s": (end_time - start_time).total_seconds(),
                "metadata": {
                    "model": getattr(llm, "model_name", str(llm)),
                    "use_fixtures": use_fixtures,
                },
            }

            if run:
                # Basic trajectory extraction from LangSmith run if available
                record["trajectory"] = {
                    "id": str(run.id),
                    "serialized": run.serialized,
                    "inputs": run.inputs,
                    "outputs": run.outputs,
                }

            # If no output_path, use default recordings directory
            if not output_path:
                recordings_dir = REPO_ROOT / "tests" / "evals" / "searcher" / "recordings"
                recordings_dir.mkdir(parents=True, exist_ok=True)
                filename = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id[:8]}.json"
                output_path = recordings_dir / filename

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, default=str)

            print(f"Run recorded to {output_path}")

        except Exception as e:
            print(f"Error during run {i + 1}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Record Searcher agent runs.")
    parser.add_argument("--question", required=True, help="The search question.")
    parser.add_argument("--output", help="Output JSON file path.")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs.")
    parser.add_argument("--context", default="", help="Execution context.")
    parser.add_argument(
        "--use-fixtures", action="store_true", help="Use fixtures instead of real network."
    )

    args = parser.parse_args()

    asyncio.run(
        record_run(
            question=args.question,
            output_path=Path(args.output) if args.output else None,
            runs=args.runs,
            context=args.context,
            use_fixtures=args.use_fixtures,
        )
    )


if __name__ == "__main__":
    main()
