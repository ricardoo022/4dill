"""Unit tests for skill loader module.

Tests validate that SKILL.md files can be parsed correctly,
descriptions are cleaned, and indices are generated.
"""

import logging

from pentest.skills.loader import (
    _clean_description,
    _parse_frontmatter,
    load_fase_index,
    load_fase_skill,
)


class TestParseFrontmatter:
    """Test YAML frontmatter parsing."""

    def test_parse_valid_frontmatter(self) -> None:
        """Parse valid frontmatter with YAML content."""
        content = """---
title: Test SKILL
description: This is a test description
fase: 1
---
# Body content
"""
        result = _parse_frontmatter(content)
        assert result["title"] == "Test SKILL"
        assert result["description"] == "This is a test description"
        assert result["fase"] == 1

    def test_parse_empty_frontmatter(self) -> None:
        """Parse empty frontmatter."""
        content = """---
---
# Body content
"""
        result = _parse_frontmatter(content)
        assert result == {}

    def test_parse_no_frontmatter(self) -> None:
        """Parse content without frontmatter."""
        content = "# Body content\nNo frontmatter here"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_parse_invalid_yaml(self) -> None:
        """Parse invalid YAML in frontmatter."""
        content = """---
invalid: yaml: content: [
---
# Body content
"""
        result = _parse_frontmatter(content)
        assert result == {}


class TestCleanDescription:
    """Test description cleaning."""

    def test_remove_execute_prefix(self) -> None:
        """Remove 'Execute FASE X -' prefix."""
        raw = "Execute FASE 1 - Reconnaissance and mapping"
        result = _clean_description("fase-1", raw)
        assert "Execute FASE" not in result
        assert result == "Reconnaissance and mapping"

    def test_remove_invoke_suffix(self) -> None:
        """Remove 'Invoke with /scan-fase-X' suffix."""
        raw = "Test description. Invoke with /scan-fase-1 {url}."
        result = _clean_description("fase-1", raw)
        assert "Invoke with" not in result
        assert "{url}" not in result

    def test_remove_both_patterns(self) -> None:
        """Remove both patterns at once."""
        raw = "Execute FASE 1 - Test description. Invoke with /scan-fase-1 {url}."
        result = _clean_description("fase-1", raw)
        assert "Execute FASE" not in result
        assert "Invoke with" not in result
        assert result == "Test description."

    def test_preserve_content(self) -> None:
        """Preserve actual content after cleaning."""
        raw = "Execute FASE 3 - RLS Testing in Supabase. Invoke with /scan-fase-3 {url}."
        result = _clean_description("fase-3", raw)
        assert "RLS Testing in Supabase" in result

    def test_already_formatted(self) -> None:
        """Preserve already-formatted description."""
        raw = "Reconnaissance — Map the attack surface and identify entry points"
        result = _clean_description("fase-1", raw)
        assert result == raw


class TestLoadFaseIndex:
    """Test SKILL file loading and index generation."""

    def test_load_single_fase(self, tmp_path) -> None:
        """Load a single fase."""
        # Create mock SKILL.md file
        skill_dir = tmp_path / "scan-fase-1"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            """---
title: Reconnaissance
description: Execute FASE 1 - Map the attack surface. Invoke with /scan-fase-1 {url}.
---
# Body
"""
        )

        result = load_fase_index(["fase-1"], str(tmp_path))
        assert "fase-1" in result
        assert "Fases disponíveis no scan_path" in result
        assert "Map the attack surface" in result
        assert "Execute FASE" not in result

    def test_load_multiple_fases(self, tmp_path) -> None:
        """Load multiple fases."""
        # Create multiple SKILL.md files
        for fase_num in [1, 3]:
            skill_dir = tmp_path / f"scan-fase-{fase_num}"
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                f"""---
description: Execute FASE {fase_num} - Test description {fase_num}. Invoke with /scan-fase-{fase_num} {{url}}.
---
# Body
"""
            )

        result = load_fase_index(["fase-1", "fase-3"], str(tmp_path))
        assert "fase-1" in result
        assert "fase-3" in result
        assert result.count("-") >= 3  # Header + at least 2 list items

    def test_missing_file_warning(self, tmp_path, caplog) -> None:
        """Missing files generate warnings but don't crash."""
        with caplog.at_level(logging.WARNING):
            result = load_fase_index(["fase-999"], str(tmp_path))

        assert "not found" in caplog.text.lower()
        assert result == ""

    def test_invalid_yaml_warning(self, tmp_path, caplog) -> None:
        """Invalid YAML generates warnings."""
        skill_dir = tmp_path / "scan-fase-1"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            """---
invalid: yaml: [
---
# Body
"""
        )

        with caplog.at_level(logging.WARNING):
            result = load_fase_index(["fase-1"], str(tmp_path))

        assert "No description" in caplog.text or "Failed to parse" in caplog.text
        assert result == ""

    def test_empty_scan_path(self, tmp_path) -> None:
        """Empty scan_path returns empty string."""
        result = load_fase_index([], str(tmp_path))
        assert result == ""

    def test_scan_prefix_already_present(self, tmp_path) -> None:
        """scan- prefix is not duplicated."""
        skill_dir = tmp_path / "scan-fase-1"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            """---
description: Test description
---
# Body
"""
        )

        result = load_fase_index(["scan-fase-1"], str(tmp_path))
        assert "Test description" in result


class TestLoadFaseSkill:
    """Test complete SKILL.md loading."""

    def test_load_skill_content(self, tmp_path) -> None:
        """Load complete SKILL.md content."""
        skill_dir = tmp_path / "scan-fase-1"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        content = """---
title: Test
---
# Body
This is the full content.
"""
        skill_file.write_text(content)

        result = load_fase_skill("fase-1", str(tmp_path))
        assert "# Body" in result
        assert "This is the full content" in result

    def test_load_skill_missing_file(self, tmp_path, caplog) -> None:
        """Load missing skill file."""
        with caplog.at_level(logging.WARNING):
            result = load_fase_skill("fase-999", str(tmp_path))

        assert "not found" in caplog.text.lower()
        assert result == ""

    def test_load_skill_with_scan_prefix(self, tmp_path) -> None:
        """Load skill with scan- prefix already present."""
        skill_dir = tmp_path / "scan-fase-1"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# Content")

        result = load_fase_skill("scan-fase-1", str(tmp_path))
        assert "# Content" in result
