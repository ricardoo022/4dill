"""Pytest fixtures for Searcher evaluation."""

import json
from pathlib import Path

import pytest

SEARCHER_DATASET_PATH = Path(__file__).parent / "datasets" / "searcher.json"


@pytest.fixture
def searcher_dataset():
    """Load the Searcher evaluation dataset."""
    if not SEARCHER_DATASET_PATH.exists():
        # Return an empty but valid structure if dataset doesn't exist yet
        return {"scenarios": []}
    with open(SEARCHER_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def searcher_fixtures_dir():
    """Path to Searcher recordings used as fixtures."""
    return Path(__file__).parent / "fixtures"
