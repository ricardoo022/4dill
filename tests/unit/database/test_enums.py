"""Unit tests for database enums (US-007).

Tests cover:
- Enum member counts match specification
- String serialization (lowercase values)
- Enum deserialization (value -> enum member)
- Error handling for invalid values
- JSON round-trip serialization
"""

import json

import pytest

from pentest.database.enums import (
    ContainerStatus,
    ContainerType,
    FlowStatus,
    MsgchainType,
    MsglogResultFormat,
    MsglogType,
    SubtaskStatus,
    TaskStatus,
    TermlogType,
    ToolcallStatus,
)


class TestEnumMemberCounts:
    """Test that each enum has the correct number of members."""

    def test_flow_status_count(self):
        """FlowStatus should have 5 members."""
        assert len(FlowStatus) == 5

    def test_task_status_count(self):
        """TaskStatus should have 5 members."""
        assert len(TaskStatus) == 5

    def test_subtask_status_count(self):
        """SubtaskStatus should have 5 members."""
        assert len(SubtaskStatus) == 5

    def test_container_type_count(self):
        """ContainerType should have 2 members."""
        assert len(ContainerType) == 2

    def test_container_status_count(self):
        """ContainerStatus should have 5 members."""
        assert len(ContainerStatus) == 5

    def test_toolcall_status_count(self):
        """ToolcallStatus should have 4 members."""
        assert len(ToolcallStatus) == 4

    def test_msgchain_type_count(self):
        """MsgchainType should have exactly 14 members."""
        assert len(MsgchainType) == 14

    def test_termlog_type_count(self):
        """TermlogType should have 3 members."""
        assert len(TermlogType) == 3

    def test_msglog_type_count(self):
        """MsglogType should have exactly 10 members."""
        assert len(MsglogType) == 10

    def test_msglog_result_format_count(self):
        """MsglogResultFormat should have 3 members."""
        assert len(MsglogResultFormat) == 3


class TestEnumStringSerializaton:
    """Test that enum values are lowercase strings."""

    def test_flow_status_created_value(self):
        """FlowStatus.CREATED.value should be 'created'."""
        assert FlowStatus.CREATED.value == "created"

    def test_flow_status_running_value(self):
        """FlowStatus.RUNNING.value should be 'running'."""
        assert FlowStatus.RUNNING.value == "running"

    def test_task_status_finished_value(self):
        """TaskStatus.FINISHED.value should be 'finished'."""
        assert TaskStatus.FINISHED.value == "finished"

    def test_container_type_primary_value(self):
        """ContainerType.PRIMARY.value should be 'primary'."""
        assert ContainerType.PRIMARY.value == "primary"

    def test_container_status_running_value(self):
        """ContainerStatus.RUNNING.value should be 'running'."""
        assert ContainerStatus.RUNNING.value == "running"

    def test_msgchain_type_primary_agent_value(self):
        """MsgchainType.PRIMARY_AGENT.value should be 'primary_agent'."""
        assert MsgchainType.PRIMARY_AGENT.value == "primary_agent"

    def test_msgchain_type_tool_call_fixer_value(self):
        """MsgchainType.TOOL_CALL_FIXER.value should be 'tool_call_fixer'."""
        assert MsgchainType.TOOL_CALL_FIXER.value == "tool_call_fixer"

    def test_termlog_type_stdout_value(self):
        """TermlogType.STDOUT.value should be 'stdout'."""
        assert TermlogType.STDOUT.value == "stdout"

    def test_msglog_type_terminal_value(self):
        """MsglogType.TERMINAL.value should be 'terminal'."""
        assert MsglogType.TERMINAL.value == "terminal"

    def test_msglog_result_format_markdown_value(self):
        """MsglogResultFormat.MARKDOWN.value should be 'markdown'."""
        assert MsglogResultFormat.MARKDOWN.value == "markdown"


class TestEnumDeserialization:
    """Test that enums can be reconstructed from their string values."""

    def test_flow_status_deserialization(self):
        """FlowStatus should deserialize from 'created' string."""
        assert FlowStatus("created") == FlowStatus.CREATED

    def test_task_status_deserialization(self):
        """TaskStatus should deserialize from 'running' string."""
        assert TaskStatus("running") == TaskStatus.RUNNING

    def test_container_status_deserialization(self):
        """ContainerStatus should deserialize from 'stopped' string."""
        assert ContainerStatus("stopped") == ContainerStatus.STOPPED

    def test_msgchain_type_deserialization(self):
        """MsgchainType should deserialize from 'generator' string."""
        assert MsgchainType("generator") == MsgchainType.GENERATOR

    def test_msglog_type_deserialization(self):
        """MsglogType should deserialize from 'advice' string."""
        assert MsglogType("advice") == MsglogType.ADVICE

    def test_msglog_result_format_deserialization(self):
        """MsglogResultFormat should deserialize from 'plain' string."""
        assert MsglogResultFormat("plain") == MsglogResultFormat.PLAIN


class TestInvalidEnumValues:
    """Test that invalid enum values raise ValueError."""

    def test_flow_status_invalid_raises(self):
        """FlowStatus with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            FlowStatus("invalid")

    def test_task_status_invalid_raises(self):
        """TaskStatus with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            TaskStatus("nonexistent")

    def test_container_status_invalid_raises(self):
        """ContainerStatus with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            ContainerStatus("unknown")

    def test_msgchain_type_invalid_raises(self):
        """MsgchainType with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            MsgchainType("bad_agent")

    def test_msglog_type_invalid_raises(self):
        """MsglogType with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            MsglogType("invalid_message")

    def test_msglog_result_format_invalid_raises(self):
        """MsglogResultFormat with invalid value should raise ValueError."""
        with pytest.raises(ValueError):
            MsglogResultFormat("html")


class TestJSONRoundtrip:
    """Test that enums serialize and deserialize correctly through JSON."""

    def test_flow_status_json_roundtrip(self):
        """FlowStatus should survive JSON serialization round-trip."""
        original = FlowStatus.RUNNING
        serialized = json.dumps(original.value)
        deserialized = FlowStatus(json.loads(serialized))
        assert deserialized == original

    def test_task_status_json_roundtrip(self):
        """TaskStatus should survive JSON serialization round-trip."""
        original = TaskStatus.FINISHED
        serialized = json.dumps(original.value)
        deserialized = TaskStatus(json.loads(serialized))
        assert deserialized == original

    def test_container_status_json_roundtrip(self):
        """ContainerStatus should survive JSON serialization round-trip."""
        original = ContainerStatus.DELETED
        serialized = json.dumps(original.value)
        deserialized = ContainerStatus(json.loads(serialized))
        assert deserialized == original

    def test_msgchain_type_json_roundtrip(self):
        """MsgchainType should survive JSON serialization round-trip."""
        original = MsgchainType.TOOL_CALL_FIXER
        serialized = json.dumps(original.value)
        deserialized = MsgchainType(json.loads(serialized))
        assert deserialized == original

    def test_msglog_type_json_roundtrip(self):
        """MsglogType should survive JSON serialization round-trip."""
        original = MsglogType.ANSWER
        serialized = json.dumps(original.value)
        deserialized = MsglogType(json.loads(serialized))
        assert deserialized == original

    def test_msglog_result_format_json_roundtrip(self):
        """MsglogResultFormat should survive JSON serialization round-trip."""
        original = MsglogResultFormat.TERMINAL
        serialized = json.dumps(original.value)
        deserialized = MsglogResultFormat(json.loads(serialized))
        assert deserialized == original

    def test_multiple_enums_json_array_roundtrip(self):
        """Multiple enums in JSON array should round-trip correctly."""
        enums = [FlowStatus.CREATED, TaskStatus.RUNNING, ContainerStatus.FAILED]
        serialized = json.dumps([e.value for e in enums])
        values = json.loads(serialized)
        deserialized = [
            FlowStatus(values[0]),
            TaskStatus(values[1]),
            ContainerStatus(values[2]),
        ]
        assert deserialized == enums


class TestMsgchainTypeMembers:
    """Test that MsgchainType has all expected members."""

    def test_all_msgchain_members_exist(self):
        """Verify all 14 MsgchainType members are defined."""
        expected = {
            "PRIMARY_AGENT",
            "REPORTER",
            "GENERATOR",
            "REFINER",
            "REFLECTOR",
            "ENRICHER",
            "ADVISER",
            "CODER",
            "MEMORIST",
            "SEARCHER",
            "INSTALLER",
            "PENTESTER",
            "SUMMARIZER",
            "TOOL_CALL_FIXER",
        }
        actual = {member.name for member in MsgchainType}
        assert actual == expected


class TestMsglogTypeMembers:
    """Test that MsglogType has all expected members."""

    def test_all_msglog_members_exist(self):
        """Verify all 10 MsglogType members are defined."""
        expected = {
            "THOUGHTS",
            "BROWSER",
            "TERMINAL",
            "FILE",
            "SEARCH",
            "ADVICE",
            "INPUT",
            "DONE",
            "ANSWER",
            "REPORT",
        }
        actual = {member.name for member in MsglogType}
        assert actual == expected
