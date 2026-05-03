import json
import os
import re
from typing import Any


class SearcherFixtureInterceptor:
    def __init__(self, fixtures_path: str, snapshots_dir: str):
        self.snapshots_dir = snapshots_dir
        with open(fixtures_path) as f:
            self.fixtures = json.load(f)
        self.call_log = []
        self.unmatched_count = 0

    def intercept(self, tool_name: str, args: dict[str, Any]) -> Any:
        # Preserve search_result
        if tool_name == "search_result":
            return None  # Fallthrough to real tool

        matched_fixture = None
        normalized_args = json.dumps(args, sort_keys=True)

        for fixture in self.fixtures:
            if fixture["tool_name"] == tool_name and re.match(
                fixture["args_pattern"], normalized_args
            ):
                matched_fixture = fixture
                break

        entry = {"tool_name": tool_name, "args": args, "matched": matched_fixture is not None}
        self.call_log.append(entry)

        if matched_fixture:
            response = matched_fixture["response"]
            if matched_fixture["source_type"] == "browser_snapshot":
                path = os.path.join(self.snapshots_dir, response["snapshot_path"])
                with open(path) as f:
                    return {"content": f.read()}
            return response

        self.unmatched_count += 1
        return self._get_fallback(tool_name)

    def _get_fallback(self, tool_name: str) -> Any:
        if tool_name == "browser":
            return {"content": "Page snapshot not found"}
        if tool_name == "search_answer":
            return "Nothing found in answer store for this query."
        return {"results": []}

    def get_call_log(self) -> list[dict[str, Any]]:
        return self.call_log

    def get_unmatched_count(self) -> int:
        return self.unmatched_count
