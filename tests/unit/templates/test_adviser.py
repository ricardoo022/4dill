from pentest.templates.adviser import render_adviser_prompt


def test_render_adviser_prompt():
    """Tests that adviser templates are rendered correctly with Jinja2."""
    question = "How to bypass Cloudflare WAF?"
    context = "ffuf returns 403 Forbidden."
    execution_context = "Tried custom headers."

    system, user = render_adviser_prompt(
        question=question, context=context, execution_context=execution_context
    )

    # Check system prompt
    assert "Role: Strategic Cybersecurity Consultant" in system
    assert "Adviser Agent" in system
    assert "Never Execute" in system

    # Check user prompt
    assert "Strategic Assistance Request" in user
    assert question in user
    assert context in user
    assert execution_context in user
    assert "Execution History" in user


def test_render_adviser_prompt_no_execution_context():
    """Tests rendering without optional execution context."""
    system, user = render_adviser_prompt(question="q", context="c")
    assert "Execution History" not in user
