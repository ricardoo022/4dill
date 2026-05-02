"""Structural evaluator: checks that Generator output is a valid subtask plan."""


def subtask_plan_valid(outputs: dict, reference_outputs: dict | None = None) -> dict:
    """Score 1.0 if output contains a valid subtask plan (1-15 tasks, each with title/description).

    Returns:
        dict with keys: key (str), score (float 0-1), comment (str)
    """
    subtasks = outputs.get("subtasks", [])

    if not isinstance(subtasks, list) or len(subtasks) == 0:
        return {
            "key": "subtask_plan_valid",
            "score": 0.0,
            "comment": f"No subtasks in output (got {type(subtasks).__name__})",
        }

    if len(subtasks) > 15:
        return {
            "key": "subtask_plan_valid",
            "score": 0.0,
            "comment": f"Too many subtasks: {len(subtasks)} (max 15)",
        }

    missing_fields = []
    for i, st in enumerate(subtasks):
        if not isinstance(st, dict):
            return {
                "key": "subtask_plan_valid",
                "score": 0.0,
                "comment": f"Subtask {i} is not a dict: {type(st).__name__}",
            }
        for field in ("title", "description"):
            if not st.get(field, "").strip():
                missing_fields.append(f"subtask[{i}].{field}")

    if missing_fields:
        partial = 1.0 - (len(missing_fields) / (len(subtasks) * 2))
        return {
            "key": "subtask_plan_valid",
            "score": round(max(0.0, partial), 2),
            "comment": f"Missing or blank fields: {', '.join(missing_fields)}",
        }

    return {
        "key": "subtask_plan_valid",
        "score": 1.0,
        "comment": f"Valid plan with {len(subtasks)} subtask(s)",
    }
