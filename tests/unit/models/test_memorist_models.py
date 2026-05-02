import pytest
from pydantic import ValidationError

from pentest.models.memorist import MemoristResult


def test_memorist_result_validation_empty_result():
    with pytest.raises(ValidationError):
        MemoristResult(result="", message="Valid message")


def test_memorist_result_validation_whitespace_result():
    with pytest.raises(ValidationError):
        MemoristResult(result="   ", message="Valid message")


def test_memorist_result_validation_empty_message():
    with pytest.raises(ValidationError):
        MemoristResult(result="Valid result", message="")


def test_memorist_result_validation_whitespace_message():
    with pytest.raises(ValidationError):
        MemoristResult(result="Valid result", message="   ")


def test_memorist_result_valid():
    valid = MemoristResult(result="Memory data found", message="Done")
    assert valid.result == "Memory data found"
    assert valid.message == "Done"


def test_memorist_result_strip():
    result = MemoristResult(result="  Data with spaces  ", message="  Done  ")
    assert result.result == "Data with spaces"
    assert result.message == "Done"
