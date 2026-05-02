from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from pentest.models.tool_args import FileAction, TerminalAction
from pentest.tools.file import create_file_tool, create_mock_file_tool
from pentest.tools.terminal import create_mock_terminal_tool, create_terminal_tool


def test_terminal_action_validation():
    with pytest.raises(ValidationError):
        TerminalAction(input="ls", timeout=5, message="msg")
    # valid
    ta = TerminalAction(input="ls -la", timeout=10, message="run list")
    assert ta.input == "ls -la"
    assert ta.timeout == 10


def test_file_action_validation():
    with pytest.raises(ValidationError):
        FileAction(action="invalid", path="/tmp/test", message="m")
    with pytest.raises(ValidationError):
        FileAction(action="read_file", path="", message="m")
    fa = FileAction(action="read_file", path="/tmp/test", message="read")
    assert fa.action == "read_file"


def test_mock_terminal_tool_executes():
    tool = create_mock_terminal_tool()
    res = tool.run(
        {"input": "echo hi", "cwd": "/work", "detach": False, "timeout": 60, "message": "t"}
    )
    assert "Mock terminal executed" in res


def test_mock_file_tool_executes():
    tool = create_mock_file_tool()
    res = tool.run({"action": "read_file", "path": "/etc/hosts", "content": None, "message": "r"})
    assert "Mock read from" in res


def test_terminal_factory_with_mock_docker():
    mock_docker = MagicMock()
    mock_docker.exec_command.return_value = "real container output"
    tool = create_terminal_tool(mock_docker, "container-1")
    res = tool.run(
        {"input": "whoami", "cwd": "/work", "detach": False, "timeout": 60, "message": "t"}
    )
    assert res == "real container output"

    # simulate an exception
    mock_docker.exec_command.side_effect = Exception("boom")
    res2 = tool.run(
        {"input": "bad", "cwd": "/work", "detach": False, "timeout": 60, "message": "t"}
    )
    assert isinstance(res2, str) and "terminal tool error" in res2


def test_file_factory_with_mock_docker():
    mock_docker = MagicMock()
    mock_docker.read_file.return_value = "file contents"
    mock_docker.write_file.return_value = "wrote ok"

    tool = create_file_tool(mock_docker, "container-1")
    r1 = tool.run({"action": "read_file", "path": "/etc/hosts", "content": None, "message": "r"})
    assert r1 == "file contents"

    r2 = tool.run({"action": "update_file", "path": "/etc/hosts", "content": "abc", "message": "u"})
    assert r2 == "wrote ok"

    # simulate exception
    mock_docker.read_file.side_effect = Exception("badread")
    r3 = tool.run({"action": "read_file", "path": "/etc/hosts", "content": None, "message": "r"})
    assert isinstance(r3, str) and "file tool error" in r3
