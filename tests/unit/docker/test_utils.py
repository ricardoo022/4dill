"""Unit tests for container naming and port allocation utilities (US-019)."""

from pentest.docker.utils import (
    BASE_CONTAINER_PORTS,
    CONTAINER_PORTS_COUNT,
    MAX_PORT_RANGE,
    WORK_FOLDER_PATH,
    get_primary_container_ports,
    primary_terminal_name,
)


class TestConstants:
    """Verify constant values match PentAGI's client.go lines 29-40."""

    def test_work_folder_path(self):
        assert WORK_FOLDER_PATH == "/work"

    def test_base_container_ports(self):
        assert BASE_CONTAINER_PORTS == 28000

    def test_container_ports_count(self):
        assert CONTAINER_PORTS_COUNT == 2

    def test_max_port_range(self):
        assert MAX_PORT_RANGE == 2000


class TestPrimaryTerminalName:
    """Verify container naming pattern: pentestai-terminal-{flow_id}."""

    def test_flow_id_1(self):
        assert primary_terminal_name(1) == "pentestai-terminal-1"

    def test_flow_id_999(self):
        assert primary_terminal_name(999) == "pentestai-terminal-999"

    def test_flow_id_0(self):
        assert primary_terminal_name(0) == "pentestai-terminal-0"


class TestGetPrimaryContainerPorts:
    """Verify deterministic port allocation formula."""

    def test_flow_id_0(self):
        """flow_id=0 -> [28000, 28001]."""
        assert get_primary_container_ports(0) == [28000, 28001]

    def test_flow_id_1(self):
        """flow_id=1 -> [28002, 28003]."""
        assert get_primary_container_ports(1) == [28002, 28003]

    def test_flow_id_2(self):
        """flow_id=2 -> [28004, 28005]."""
        assert get_primary_container_ports(2) == [28004, 28005]

    def test_flow_id_1000_wraps_around(self):
        """flow_id=1000 wraps: (1000*2) % 2000 == 0 -> [28000, 28001]."""
        assert get_primary_container_ports(1000) == [28000, 28001]

    def test_returns_exactly_two_ports(self):
        assert len(get_primary_container_ports(42)) == 2

    def test_ports_are_integers(self):
        ports = get_primary_container_ports(5)
        assert all(isinstance(p, int) for p in ports)


class TestPortUniqueness:
    """100 consecutive flow IDs must all produce unique port pairs."""

    def test_unique_port_pairs(self):
        seen: set[tuple[int, ...]] = set()
        for flow_id in range(100):
            pair = tuple(get_primary_container_ports(flow_id))
            assert pair not in seen, f"Duplicate ports for flow_id={flow_id}: {pair}"
            seen.add(pair)
        assert len(seen) == 100
