"""US-054 tests for Searcher Pydantic models."""

import pytest
from pydantic import ValidationError

from pentest.models.search import ComplexSearch, SearchAction, SearchAnswerAction, SearchResult


def test_complex_search_valid_pentest_query() -> None:
    """US-054: ComplexSearch accepts required question and message fields."""
    action = ComplexSearch(
        question="Find CVEs for OpenSSH 8.9p1 exposed on port 22",
        message="Research known OpenSSH vulnerabilities",
    )
    assert action.question == "Find CVEs for OpenSSH 8.9p1 exposed on port 22"
    assert action.message == "Research known OpenSSH vulnerabilities"


def test_complex_search_rejects_empty_question() -> None:
    """US-054: ComplexSearch rejects an empty required question."""
    with pytest.raises(ValidationError):
        ComplexSearch(question="", message="Research vulnerabilities")


def test_search_action_valid_query_defaults_and_bounds() -> None:
    """US-054: SearchAction accepts a valid query, bounded max_results, and message."""
    action = SearchAction(
        query="CVE OpenSSH 8.9p1 privilege escalation",
        max_results=5,
        message="Look for exploit references and advisories",
    )
    assert action.query == "CVE OpenSSH 8.9p1 privilege escalation"
    assert action.max_results == 5
    assert action.message == "Look for exploit references and advisories"


def test_search_action_rejects_max_results_below_min() -> None:
    """US-054: SearchAction rejects max_results below 1."""
    with pytest.raises(ValidationError):
        SearchAction(
            query="Django 3.2 SQL injection CVE",
            max_results=0,
            message="Collect primary advisories",
        )


def test_search_action_rejects_max_results_above_max() -> None:
    """US-054: SearchAction rejects max_results above 10."""
    with pytest.raises(ValidationError):
        SearchAction(
            query="Django 3.2 SQL injection CVE",
            max_results=11,
            message="Collect primary advisories",
        )


def test_search_result_valid_report_and_message() -> None:
    """US-054: SearchResult accepts result and localized summary message."""
    result = SearchResult(
        result=(
            "Multiple references indicate CVE-2023-38408 may allow remote code execution "
            "in certain OpenSSH agent forwarding scenarios."
        ),
        message="Encontradas referencias para CVE-2023-38408 no OpenSSH.",
    )
    assert "CVE-2023-38408" in result.result
    assert result.message == "Encontradas referencias para CVE-2023-38408 no OpenSSH."


def test_search_answer_action_valid_single_question() -> None:
    """US-054: SearchAnswerAction accepts one semantic question with a valid type."""
    action = SearchAnswerAction(
        questions=["How to verify if CVE-2023-38408 affects OpenSSH 8.9p1?"],
        type="guide",
        message="Search internal KB for remediation guidance",
    )
    assert action.questions == ["How to verify if CVE-2023-38408 affects OpenSSH 8.9p1?"]
    assert action.type == "guide"
    assert action.message == "Search internal KB for remediation guidance"


def test_search_answer_action_rejects_empty_questions_list() -> None:
    """US-054: SearchAnswerAction enforces minimum list length of 1."""
    with pytest.raises(ValidationError):
        SearchAnswerAction(
            questions=[],
            type="guide",
            message="Search KB for exploit prerequisites",
        )


def test_search_answer_action_rejects_too_many_questions() -> None:
    """US-054: SearchAnswerAction enforces maximum list length of 5."""
    with pytest.raises(ValidationError):
        SearchAnswerAction(
            questions=[
                "OpenSSH CVE impact on Ubuntu 22.04",
                "OpenSSH CVE impact on Debian 12",
                "OpenSSH CVE impact on Alpine 3.20",
                "OpenSSH CVE exploitability over exposed SSH port",
                "OpenSSH CVE mitigation checklist",
                "OpenSSH CVE patch backport references",
            ],
            type="guide",
            message="Search KB for platform-specific impact",
        )


def test_search_result_rejects_empty_result() -> None:
    """US-054: SearchResult rejects an empty result field."""
    with pytest.raises(ValidationError):
        SearchResult(result="", message="Nenhum resultado encontrado")


def test_search_result_rejects_empty_message() -> None:
    """US-054: SearchResult rejects an empty message field."""
    with pytest.raises(ValidationError):
        SearchResult(result="Found CVE references", message="")


def test_search_answer_action_rejects_invalid_type() -> None:
    """US-054: SearchAnswerAction rejects values outside the allowed literal set."""
    with pytest.raises(ValidationError):
        SearchAnswerAction(
            questions=["Where is the exploit PoC for CVE-2023-38408?"],
            type="exploit",
            message="Find exploit implementation details",
        )


def test_search_answer_action_rejects_empty_question_item() -> None:
    """US-054: SearchAnswerAction rejects whitespace-only items in questions."""
    with pytest.raises(ValidationError):
        SearchAnswerAction(
            questions=["q1", "   "],
            type="guide",
            message="Search in KB",
        )


@pytest.mark.parametrize(
    ("model_cls", "expected_properties", "expected_required"),
    [
        (ComplexSearch, {"question", "message"}, {"question", "message"}),
        (SearchAction, {"query", "max_results", "message"}, {"query", "message"}),
        (SearchResult, {"result", "message"}, {"result", "message"}),
        (SearchAnswerAction, {"questions", "type", "message"}, {"questions", "type", "message"}),
    ],
)
def test_all_search_models_json_schema_function_calling_shape(
    model_cls: type,
    expected_properties: set[str],
    expected_required: set[str],
) -> None:
    """US-054: Every Searcher model schema contains properties and required keys."""
    schema = model_cls.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "required" in schema
    assert expected_properties.issubset(set(schema["properties"].keys()))
    assert expected_required.issubset(set(schema["required"]))
