"""E2E coverage for Searcher eval infrastructure."""

import asyncio
import json

import pytest

from tests.evals.searcher.record_search_run import record_run


@pytest.mark.e2e
def test_record_search_run_fixture_round_trip_e2e(tmp_path):
    """Validate record_run round-trip with fixture-backed execution."""
    fixture_file = tmp_path / "fixture_run.json"
    output_file = tmp_path / "recorded_run.json"

    fixture_file.write_text(
        json.dumps(
            {
                "output": "E2E fixture answer",
                "tool_calls": [
                    {
                        "name": "tavily_search",
                        "input": "{'query': 'nginx stable version'}",
                        "output": "1.30.0",
                    },
                    {
                        "name": "search_result",
                        "input": "{'result': 'E2E fixture answer'}",
                        "output": "ok",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    asyncio.run(
        record_run(
            question="What is nginx latest stable version?",
            output_path=output_file,
            use_fixtures=True,
            fixture_path=fixture_file,
        )
    )

    assert output_file.exists()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["output"] == "E2E fixture answer"
    assert len(data["tool_calls"]) == 2
    assert data["tool_calls"][0]["name"] == "tavily_search"
