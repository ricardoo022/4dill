"""Tests for Searcher evaluation infrastructure."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_searcher_eval_structure():
    """Verify the Searcher eval directory structure exists."""
    base_dir = Path("tests/evals/searcher")
    assert base_dir.exists()
    assert (base_dir / "__init__.py").exists()
    assert (base_dir / "datasets").is_dir()
    assert (base_dir / "evaluators").is_dir()
    assert (base_dir / "fixtures").is_dir()
    assert (base_dir / "recordings").is_dir()


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


def test_run_searcher_eval_no_upload():
    """Verify run_searcher_eval.py --no-upload runs with placeholder."""
    # We use a non-existent dataset to trigger placeholder creation
    dataset_path = Path("tests/evals/searcher/datasets/test_placeholder.json")
    if dataset_path.exists():
        dataset_path.unlink()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    result = subprocess.run(
        [
            sys.executable,
            "tests/evals/searcher/run_searcher_eval.py",
            "--no-upload",
            "--dataset",
            str(dataset_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert "Creating placeholder dataset" in result.stdout
    assert (
        "Summary: 0/1 successful runs" in result.stdout
        or "Summary: 1/1 successful runs" in result.stdout
    )
    assert dataset_path.exists()


def test_run_searcher_eval_help_includes_upload_flag():
    """Verify run_searcher_eval.py exposes --upload/--no-upload flags."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    result = subprocess.run(
        [sys.executable, "tests/evals/searcher/run_searcher_eval.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert "--upload" in result.stdout
    assert "--no-upload" in result.stdout


def test_record_search_run_produces_json(tmp_path, mocker):
    """Verify record_search_run.py produces a valid JSON with tool calls."""
    output_file = tmp_path / "test_run.json"

    # Mock perform_search to avoid real LLM calls
    # We need to mock it in the subprocess or run it in-process
    # Running in-process is easier for mocking
    from tests.evals.searcher.record_search_run import record_run

    mock_perform = mocker.patch(
        "tests.evals.searcher.record_search_run.perform_search", autospec=True
    )
    mock_perform.return_value = "Mocked search result"

    import asyncio

    asyncio.run(record_run(question="test question", output_path=output_file))

    assert output_file.exists()
    with open(output_file, encoding="utf-8") as f:
        data = json.load(f)
        assert data["inputs"]["question"] == "test question"
        assert data["output"] == "Mocked search result"
        assert "run_id" in data
        assert "tool_calls" in data


def test_record_search_run_use_fixtures_skips_network(tmp_path, mocker):
    """Verify --use-fixtures reads fixtures and bypasses perform_search."""
    output_file = tmp_path / "fixture_run.json"
    fixture_file = tmp_path / "fixture_input.json"
    fixture_file.write_text(
        json.dumps(
            {
                "output": "Fixture answer",
                "tool_calls": [{"name": "duckduckgo", "input": "q", "output": "ok"}],
            }
        ),
        encoding="utf-8",
    )

    from tests.evals.searcher.record_search_run import record_run

    mock_perform = mocker.patch(
        "tests.evals.searcher.record_search_run.perform_search", autospec=True
    )

    import asyncio

    asyncio.run(
        record_run(
            question="fixture question",
            output_path=output_file,
            use_fixtures=True,
            fixture_path=fixture_file,
        )
    )

    mock_perform.assert_not_called()
    with open(output_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["output"] == "Fixture answer"
    assert data["tool_calls"][0]["name"] == "duckduckgo"
