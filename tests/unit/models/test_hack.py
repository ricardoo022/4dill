import pytest
from pydantic import ValidationError

from pentest.models.hack import HackResult


def test_hack_result_validation():
    # Sucesso
    valid = HackResult(result="Technical report", message="Short summary")
    assert valid.result == "Technical report"
    assert valid.message == "Short summary"

    # Erro: result vazio
    with pytest.raises(ValidationError) as exc:
        HackResult(result="", message="Summary")
    assert "Field cannot be blank or whitespace" in str(exc.value)

    # Erro: message apenas espaços
    with pytest.raises(ValidationError) as exc:
        HackResult(result="Report", message="   ")
    assert "Field cannot be blank or whitespace" in str(exc.value)


def test_hack_result_trimming():
    # Testar se faz strip
    result = HackResult(result="  Report with spaces  ", message="  Summary  ")
    assert result.result == "Report with spaces"
    assert result.message == "Summary"
