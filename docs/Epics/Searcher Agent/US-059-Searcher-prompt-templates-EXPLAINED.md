---
tags: [agents]
---

---
tags: [agents]
---

# US-059: Searcher prompt templates - EXPLAINED

## Architecture Decisions

The Searcher agent requires specific instructions to perform efficient and authorized searches during a penetration test. We have implemented Jinja2 templates for both the system prompt and the user message to ensure flexibility and consistency.

### Template Location and Naming
Following the project's existing patterns, we have separated the template rendering logic from the templates themselves.
- **Templates:** Located at `src/pentest/templates/searcher_system.md` and `src/pentest/templates/searcher_user.md`.
- **Renderer:** Implemented in `src/pentest/templates/searcher.py`.

We used the `.md` extension as requested in the User Story, while reusing the `Jinja2.Environment` setup similar to the Generator Agent.

### System Prompt Design
The system prompt defines the Searcher's role, authorization level, available tools, source priority, and efficiency rules.
- **Authorization:** Explicitly states that the test is pre-authorized, removing the need for disclaimers.
- **Dynamic Tools:** Uses `{{ available_tools }}` to list only the tools that are actually available to the agent.
- **Source Priority:** Encourages using local knowledge bases (`search_answer`) before resorting to web searches (`duckduckgo`, `tavily`) or specific page browsing (`browser`).
- **Efficiency:** Implements rules to limit the number of actions and tools used to prevent infinite loops and reduce latency.
- **Delivery Protocol:** Mandates the use of the `search_result` tool for the final response.

### User Message Design
The user message template is structured to provide the agent with all necessary context while remaining simple.
- **Mandatory:** `{{ question }}`.
- **Optional:** `{{ task }}`, `{{ subtask }}`, and `{{ execution_context }}` to provide situational awareness.

## Models and Queries

This US focuses on template rendering and does not involve direct database queries or SQLAlchemy models. It utilizes the `jinja2` library for text processing.

## How to Run Tests

To verify the implementation of the Searcher templates, you can run the following command:

```bash
pytest tests/unit/templates/test_searcher_templates.py -v
```

This test suite ensures that:
- Both system and user prompts are rendered correctly.
- Mandatory and optional fields are handled appropriately.
- The system prompt contains all required instructions and follows the specified priorities.
- No unauthorized instructions (like `store_answer`) are included.
