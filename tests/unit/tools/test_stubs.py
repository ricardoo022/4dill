"""Unit tests for stub tool implementations.

Tests validate that stub tools:
1. Accept valid Pydantic schemas (Layer 1)
2. Return expected placeholder messages (Layer 1)
3. Execute without errors
"""

import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import ValidationError

from pentest.models.search import ComplexSearch
from pentest.models.tool_args import MemoristAction
from pentest.tools.stubs import memorist, searcher


class MemoristActionFactory(ModelFactory):
    """Factory for generating MemoristAction instances."""

    __model__ = MemoristAction


class ComplexSearchFactory(ModelFactory):
    """Factory for generating ComplexSearch instances."""

    __model__ = ComplexSearch


def test_memorist_action_validation():
    """MemoristAction validates required fields."""
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        MemoristAction(question="test")  # Missing message

    with pytest.raises(ValidationError):
        MemoristAction(message="test")  # Missing question

    # Valid instance
    action = MemoristAction(question="What was found?", message="test")
    assert action.question == "What was found?"
    assert action.message == "test"


def test_complex_search_validation():
    """ComplexSearch validates required fields."""
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        ComplexSearch(question="test")  # Missing message

    with pytest.raises(ValidationError):
        ComplexSearch(message="test")  # Missing question

    # Valid instance
    action = ComplexSearch(question="Find CVEs", message="test")
    assert action.question == "Find CVEs"
    assert action.message == "test"


def test_memorist_action_factory():
    """MemoristActionFactory generates valid instances."""
    action = MemoristActionFactory.build()
    assert isinstance(action, MemoristAction)
    assert isinstance(action.question, str)
    assert isinstance(action.message, str)
    assert len(action.question) > 0
    assert len(action.message) > 0


def test_complex_search_factory():
    """ComplexSearchFactory generates valid instances."""
    action = ComplexSearchFactory.build()
    assert isinstance(action, ComplexSearch)
    assert isinstance(action.question, str)
    assert isinstance(action.message, str)
    assert len(action.question) > 0
    assert len(action.message) > 0


def test_memorist_tool_returns_stub_message():
    """Memorist tool returns exact stub message."""
    result = memorist.run(
        {"question": "What was previously found?", "message": "Query previous scan"}
    )
    expected = (
        "No previous scan data available. The Memorist agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected


def test_searcher_tool_returns_stub_message():
    """Searcher tool returns exact stub message."""
    result = searcher.run(
        {"question": "Find CVEs for Django 3.2", "message": "Search external sources"}
    )
    expected = (
        "External search is not yet available. The Searcher agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected


def test_memorist_tool_with_factory_input():
    """Memorist tool accepts factory-generated input."""
    action = MemoristActionFactory.build()
    result = memorist.run({"question": action.question, "message": action.message})
    expected = (
        "No previous scan data available. The Memorist agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected


def test_searcher_tool_with_factory_input():
    """Searcher tool accepts factory-generated input."""
    action = ComplexSearchFactory.build()
    result = searcher.run({"question": action.question, "message": action.message})
    expected = (
        "External search is not yet available. The Searcher agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected
