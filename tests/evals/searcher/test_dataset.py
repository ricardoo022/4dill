import json
from pathlib import Path


def test_searcher_dataset_valid() -> None:
    dataset_path = Path("tests/evals/searcher/datasets/searcher.json")
    assert dataset_path.exists(), "Dataset file should exist"

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list), "Dataset must be a JSON array"
    assert len(data) == 12, "Dataset must have exactly 12 scenarios"

    questions: set[str] = set()
    memory_count = 0
    browser_count = 0

    for item in data:
        # Check basic structure
        assert "inputs" in item
        assert "question" in item["inputs"]
        assert "reference_outputs" in item
        assert "required_facts" in item["reference_outputs"]
        assert "metadata" in item
        assert "category" in item["metadata"]
        assert "difficulty" in item["metadata"]

        # Check no duplicates
        q = item["inputs"]["question"]
        assert q not in questions, f"Duplicate question found: {q}"
        questions.add(q)

        # Check category requirements
        cat = item["metadata"]["category"]
        if cat == "memory":
            memory_count += 1
            assert "search_answer" in item["reference_outputs"]["expected_tools"]
        elif cat == "browser_followup":
            browser_count += 1
            assert "browser" in item["reference_outputs"]["expected_tools"]

        # Check acceptable sources are valid strings
        sources = item["reference_outputs"].get("acceptable_sources", [])
        for s in sources:
            assert isinstance(s, str)
            assert len(s) > 0

    # Specific quota constraints
    assert memory_count >= 3, "Must have at least 3 'memory' scenarios"
    assert browser_count >= 3, "Must have at least 3 'browser_followup' scenarios"
