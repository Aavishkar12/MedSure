"""Red-flag rule engine. Deterministic only — no LLM here.

Owned by the OCR/Rules teammate. The backend only depends on this signature.
"""


def evaluate(answers: dict, discharge_card: dict | None) -> list[dict]:
    """Return flags like {"code": "fever_high", "severity": "attention", "message": "..."}."""
    return []
