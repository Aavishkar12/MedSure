"""Red-flag rule engine. Deterministic only — no LLM here.

Owned by the OCR/Rules teammate. The backend only depends on this signature.
"""

LEVELS = {
    1: {"code": "checkin_watch", "severity": "attention", "message": "Today's check-in has an answer worth keeping an eye on."},
    2: {"code": "checkin_urgent", "severity": "urgent", "message": "Today's check-in has an answer that needs help now."},
}


def evaluate(answers: dict, discharge_card: dict | None) -> list[dict]:
    """Return flags like {"code": "fever_high", "severity": "attention", "message": "..."}.

    The app scores each check-in answer 0 (fine), 1 (watch) or 2 (urgent) and sends the highest as "level".
    """
    level = answers.get("level")
    if isinstance(level, int) and not isinstance(level, bool) and level >= 1:
        return [LEVELS[min(level, 2)]]
    return []
