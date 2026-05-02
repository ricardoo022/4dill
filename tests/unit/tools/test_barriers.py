import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from pentest.agents.base import create_agent_graph
from pentest.models.search import SearchResult
from pentest.models.subtask import SubtaskInfo, SubtaskList
from pentest.tools.barriers import memorist_result, search_result, subtask_list


def test_subtask_info_validation():
    with pytest.raises(ValidationError):
        SubtaskInfo(title="", description="Valid description")

    with pytest.raises(ValidationError):
        SubtaskInfo(title="Valid title", description="   ")

    # Testa com fase None (opcional)
    valid_subtask = SubtaskInfo(title="Valid title", description="Valid description")
    assert valid_subtask.title == "Valid title"
    assert valid_subtask.fase is None

    # Testa com fase preenchida
    valid_with_fase = SubtaskInfo(title="Title", description="Desc", fase="scan-fase-3")
    assert valid_with_fase.fase == "scan-fase-3"


def test_subtask_list_validation():
    with pytest.raises(ValidationError):
        SubtaskList(subtasks=[], message="Test message")

    with pytest.raises(ValidationError):
        SubtaskList(
            subtasks=[SubtaskInfo(title="Task", description="Desc")] * 16, message="Test message"
        )

    valid_list = SubtaskList(
        subtasks=[SubtaskInfo(title="Task", description="Desc")], message="Test message"
    )
    assert len(valid_list.subtasks) == 1


def test_subtask_list_tool():
    invoke_args = {
        "subtasks": [
            {"title": "Task 1", "description": "Description 1", "fase": "scan-fase-1"},
            {"title": "Task 2", "description": "Description 2"},
            {"title": "Task 3", "description": "Description 3"},
        ],
        "message": "Final plan",
    }

    result = subtask_list.invoke(invoke_args)
    assert result == "subtask list successfully processed with 3 subtasks"


def test_tool_json_schema():
    """Test: JSON schema tem os campos correctos para function calling"""
    schema = subtask_list.args_schema.model_json_schema()

    assert "subtasks" in schema["properties"]
    assert "message" in schema["properties"]
    assert schema["properties"]["subtasks"]["type"] == "array"


def test_graph_integration_with_subtask_list():
    """Test: Integração com graph: após barrier, state['barrier_result']['subtasks'] contém a lista"""
    mock_llm = RunnableLambda(
        lambda x: AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subtask_list",
                    "args": {
                        "subtasks": [
                            {"title": "Schema discovery", "description": "Desc", "fase": "fase-2"}
                        ],
                        "message": "Done",
                    },
                    "id": "call_abc",
                }
            ],
        )
    )
    # Ignora o bind_tools no mock
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [subtask_list], barrier_names=["subtask_list"])
    result = graph.invoke({"messages": [HumanMessage(content="Make plan")]})

    assert result.get("barrier_hit") is True
    assert "subtasks" in result["barrier_result"]
    assert len(result["barrier_result"]["subtasks"]) == 1
    assert result["barrier_result"]["subtasks"][0]["title"] == "Schema discovery"


def test_search_result_validation():
    with pytest.raises(ValidationError):
        SearchResult(result="", message="Found")

    with pytest.raises(ValidationError):
        SearchResult(result="Found details", message="   ")

    valid_result = SearchResult(result="Found details", message="Encontrado")
    assert valid_result.result == "Found details"


def test_search_result_tool():
    invoke_args = {"result": "Found CVEs", "message": "Encontrados CVEs"}
    result = search_result.invoke(invoke_args)
    assert result == "search result successfully processed"


def test_search_result_tool_json_schema():
    schema = search_result.args_schema.model_json_schema()
    assert "result" in schema["properties"]
    assert "message" in schema["properties"]
    assert "result" in schema["required"]
    assert "message" in schema["required"]


def test_graph_integration_with_search_result():
    mock_llm = RunnableLambda(
        lambda x: AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_result",
                    "args": {
                        "result": "Detailed report in English",
                        "message": "Resumo para o utilizador",
                    },
                    "id": "call_search_result",
                }
            ],
        )
    )
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [search_result], barrier_names=["search_result"])
    result = graph.invoke({"messages": [HumanMessage(content="Search target for vulnerabilities")]})

    assert result.get("barrier_hit") is True
    assert result["barrier_result"]["result"] == "Detailed report in English"
    assert result["barrier_result"]["message"] == "Resumo para o utilizador"


def test_memorist_result_validation():
    with pytest.raises(ValidationError):
        memorist_result.invoke({"result": "", "message": "Found"})

    with pytest.raises(ValidationError):
        memorist_result.invoke({"result": "Data", "message": "   "})

    result = memorist_result.invoke({"result": "Memory data", "message": "Done"})
    assert result == "memorist result successfully processed"


def test_memorist_result_tool():
    invoke_args = {"result": "Found CVEs in memory", "message": "Encontrados CVEs"}
    result = memorist_result.invoke(invoke_args)
    assert result == "memorist result successfully processed"


def test_memorist_result_tool_json_schema():
    schema = memorist_result.args_schema.model_json_schema()
    assert "result" in schema["properties"]
    assert "message" in schema["properties"]
    assert "result" in schema["required"]
    assert "message" in schema["required"]


def test_graph_integration_with_memorist_result():
    mock_llm = RunnableLambda(
        lambda x: AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "memorist_result",
                    "args": {
                        "result": "Detailed memory report",
                        "message": "Resumo da memória",
                    },
                    "id": "call_memorist_result",
                }
            ],
        )
    )
    mock_llm.bind_tools = lambda tools: mock_llm

    graph = create_agent_graph(mock_llm, [memorist_result], barrier_names=["memorist_result"])
    result = graph.invoke({"messages": [HumanMessage(content="Search memory for vulnerabilities")]})

    assert result.get("barrier_hit") is True
    assert result["barrier_result"]["result"] == "Detailed memory report"
    assert result["barrier_result"]["message"] == "Resumo da memória"
