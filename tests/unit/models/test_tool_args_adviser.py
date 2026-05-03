import pytest
from pydantic import ValidationError

from pentest.models.tool_args import AdviserInput


def test_adviser_input_validation():
    """Tests that AdviserInput validates required fields and non-empty strings."""
    # Happy path
    valid_input = AdviserInput(
        question="How to bypass Cloudflare WAF?",
        context="ffuf returns 403 for all common paths.",
        execution_context="Tried changing User-Agent.",
    )
    assert valid_input.question == "How to bypass Cloudflare WAF?"
    assert valid_input.context == "ffuf returns 403 for all common paths."
    assert valid_input.execution_context == "Tried changing User-Agent."

    # Missing question
    with pytest.raises(ValidationError):
        AdviserInput(context="some context")

    # Empty question
    with pytest.raises(ValidationError):
        AdviserInput(question="", context="some context")

    # Missing context
    with pytest.raises(ValidationError):
        AdviserInput(question="some question")

    # Empty context
    with pytest.raises(ValidationError):
        AdviserInput(question="some question", context="")

    # Optional execution_context
    minimal_input = AdviserInput(question="q", context="c")
    assert minimal_input.execution_context == ""
