from pathlib import Path

import pytest

from pentest.templates import render_scanner_prompt


@pytest.mark.agent
def test_render_scanner_prompt_basic_rendering():
    """
    Tests basic rendering of scanner system and user prompts without a specific phase skill.
    AC: templates/scanner_system.md and templates/scanner_user.md rendered correctly.
    """
    question = "Perform a service scan on 192.168.1.10"
    execution_context = "Initial network scan found 192.168.1.10 alive."
    docker_image = "kali-linux/kali-rolling"
    cwd = "/home/pentester"
    container_ports = [80, 443]
    tool_names = ["terminal", "file", "hack_result", "searcher"]
    current_time = "2026-05-02 10:00:00"

    system_prompt, user_prompt = render_scanner_prompt(
        question=question,
        execution_context=execution_context,
        docker_image=docker_image,
        cwd=cwd,
        container_ports=container_ports,
        tool_names=tool_names,
        current_time=current_time,
    )

    # Assertions for system prompt
    assert "Expert Pentester/Scanner Agent" in system_prompt
    assert f"Docker Image:** {docker_image}" in system_prompt
    assert f"Working Directory:** {cwd}" in system_prompt
    assert "Exposed Ports:** 80, 443" in system_prompt
    assert execution_context in system_prompt
    assert "terminal, file, hack_result, searcher" in system_prompt
    assert f"Use current time {current_time}" in system_prompt
    assert "## Delegation Rules" in system_prompt
    assert "searcher" in system_prompt
    assert "coder" in system_prompt
    assert "installer" in system_prompt
    assert "memorist" in system_prompt
    assert "adviser" in system_prompt
    assert "hack_result" in system_prompt

    # Assertions for user prompt
    assert "This is a fully authorized penetration testing engagement" in user_prompt
    assert f"Your Subtask:\n{question}" in user_prompt
    assert "Relevant Context from Orchestrator:" in user_prompt
    assert execution_context in user_prompt


@pytest.mark.agent
def test_render_scanner_prompt_with_skill_injection(tmp_path):
    """
    Tests dynamic injection of FASE skill into the system prompt.
    AC: fase_skill is injected INTO the system prompt.
    """
    # Setup temporary skills directory
    skills_dir = tmp_path / "skills"
    fase_name = "fase-1"
    fase_dir = skills_dir / f"scan-{fase_name}"
    fase_dir.mkdir(parents=True)

    skill_content = "---\ndescription: Scan ports 80 and 443.\n---\n# FASE 1 - Port Scanning\nUse nmap to scan ports."
    skill_file = fase_dir / "SKILL.md"
    skill_file.write_text(skill_content, encoding="utf-8")

    system_prompt, user_prompt = render_scanner_prompt(
        question="Scan target",
        execution_context="Target identified",
        docker_image="alpine",
        cwd="/",
        container_ports=[],
        tool_names=["terminal"],
        fase=fase_name,
        skills_dir=str(skills_dir),
    )

    assert "# FASE 1 - Port Scanning" in system_prompt
    assert "Use nmap to scan ports." in system_prompt
    # Ensure default message is NOT present
    assert "Execute the subtask using your general pentesting expertise" not in system_prompt


@pytest.mark.agent
def test_render_scanner_prompt_real_repo_integration():
    """
    Tests integration with real 'lusitai-internal-scan' repo skills.
    AC: Uses load_fase_skill(fase, skills_dir) to fetch content.
    """
    repo_root = Path(__file__).resolve().parents[2]
    skills_dir = repo_root / "lusitai-internal-scan" / ".claude" / "skills"

    assert skills_dir.exists(), f"Expected real skills directory at {skills_dir}"

    fase = "fase-0"

    system_prompt, user_prompt = render_scanner_prompt(
        question="Initialize scan",
        execution_context="Starting",
        docker_image="kali",
        cwd="/root",
        container_ports=[],
        tool_names=["hack_result"],
        fase=fase,
        skills_dir=str(skills_dir),
    )

    # We expect real FASE 0 instructions to be injected
    assert "hack_result" in system_prompt
    assert "FASE 0" in system_prompt
    assert "Initialize scan" in user_prompt
    assert len(system_prompt) > 500
