import json
import os
import re
from typing import Any


def extract_fixtures(recordings_dir: str, output_dir: str) -> None:
    fixtures: list[dict[str, Any]] = []
    snapshot_dir = os.path.join(output_dir, "browser_snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)

    for filename in os.listdir(recordings_dir):
        if not filename.endswith(".json"):
            continue

        with open(os.path.join(recordings_dir, filename)) as f:
            data = json.load(f)
            # Assuming recorded structure: list of {tool_name, args, response}
            for entry in data:
                tool_name = entry.get("tool_name")
                args = entry.get("args")
                response = entry.get("response")

                # Normalize args for pattern matching
                # Create a regex that ignores whitespace and handles variations in phrasing
                json_args = json.dumps(args, sort_keys=True)
                # Escape the JSON and then replace escaped quotes or braces if needed to make it regex-friendly
                # For now, let's treat it as a flexible match for common keys
                args_pattern = re.sub(r"\s+", r"\\s*", re.escape(json_args))

                fixture = {
                    "tool_name": tool_name,
                    "args_pattern": f"^{args_pattern}$",
                    "response": response,
                    "scenario": filename.replace(".json", ""),
                    "source_type": "live_web",
                }

                if tool_name == "browser":
                    # Extract snapshot content
                    snapshot_filename = f"{len(fixtures)}.html"
                    with open(os.path.join(snapshot_dir, snapshot_filename), "w") as sf:
                        sf.write(response.get("content", ""))
                    fixture["source_type"] = "browser_snapshot"
                    fixture["response"] = {"snapshot_path": snapshot_filename}

                fixtures.append(fixture)

    with open(os.path.join(output_dir, "searcher_fixtures.json"), "w") as f:
        json.dump(fixtures, f, indent=2)


if __name__ == "__main__":
    extract_fixtures("tests/evals/searcher/recordings/", "tests/evals/searcher/fixtures/")
