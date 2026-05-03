import json

import pytest

from tests.evals.searcher.interceptor import SearcherFixtureInterceptor


@pytest.fixture
def fixtures_dir(tmp_path):
    d = tmp_path / "fixtures"
    d.mkdir()
    (d / "browser_snapshots").mkdir()

    fixtures = [
        {
            "tool_name": "duckduckgo",
            "args_pattern": ".*query.*test.*",
            "response": {"results": ["test1", "test2"]},
            "scenario": "test_scenario",
            "source_type": "live_web",
        }
    ]
    with open(d / "searcher_fixtures.json", "w") as f:
        json.dump(fixtures, f)

    return d


def test_interceptor_matches_and_returns_data(fixtures_dir):
    interceptor = SearcherFixtureInterceptor(
        fixtures_dir / "searcher_fixtures.json", fixtures_dir / "browser_snapshots"
    )

    response = interceptor.intercept("duckduckgo", {"query": "test"})
    assert response == {"results": ["test1", "test2"]}
    assert interceptor.get_unmatched_count() == 0


def test_interceptor_handles_unmatched(fixtures_dir):
    interceptor = SearcherFixtureInterceptor(
        fixtures_dir / "searcher_fixtures.json", fixtures_dir / "browser_snapshots"
    )

    response = interceptor.intercept("duckduckgo", {"query": "unknown"})
    assert response == {"results": []}
    assert interceptor.get_unmatched_count() == 1


def test_interceptor_preserves_search_result(fixtures_dir):
    interceptor = SearcherFixtureInterceptor(
        fixtures_dir / "searcher_fixtures.json", fixtures_dir / "browser_snapshots"
    )

    response = interceptor.intercept("search_result", {"data": "stuff"})
    assert response is None
