import json

from tests.evals.searcher.extract_search_fixtures import extract_fixtures


def test_extract_fixtures(tmp_path):
    # Setup
    recordings_dir = tmp_path / "recordings"
    output_dir = tmp_path / "fixtures"
    recordings_dir.mkdir()

    # Dummy recording
    data = [
        {
            "tool_name": "duckduckgo",
            "args": {"query": "CVE-2023-1234"},
            "response": "Found exploit info",
        },
        {
            "tool_name": "browser",
            "args": {"url": "http://example.com"},
            "response": {"content": "<html>Example</html>"},
        },
    ]
    with open(recordings_dir / "test.json", "w") as f:
        json.dump(data, f)

    extract_fixtures(str(recordings_dir), str(output_dir))

    # Verify
    assert (output_dir / "searcher_fixtures.json").exists()
    with open(output_dir / "searcher_fixtures.json") as f:
        fixtures = json.load(f)

    assert len(fixtures) == 2
    assert fixtures[0]["tool_name"] == "duckduckgo"
    assert fixtures[1]["tool_name"] == "browser"
    assert fixtures[1]["source_type"] == "browser_snapshot"
    assert (output_dir / "browser_snapshots" / "1.html").exists()
