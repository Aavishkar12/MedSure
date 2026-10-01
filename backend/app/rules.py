"""Red-flag rules engine.

Fixed rules set the status. An LLM never decides it, and the free-text note never changes it.
These rules mirror the app's check-in: each answer maps to 0 (clear), 1 (amber) or 2 (red).
"""
from typing import Literal

Breathing = Literal["normal", "harder", "hard_resting"]
Swelling = Literal["none", "same", "more"]
Medicine = Literal["none", "dizzy", "rash", "stomach"]

BREATHING = {"normal": 0, "harder": 1, "hard_resting": 2}
SWELLING = {"none": 0, "same": 0, "more": 1}
MEDICINE = {"none": 0, "dizzy": 1, "rash": 1, "stomach": 1}

PHRASES = {
    ("breathing", "harder"): "breathing a little harder than usual",
    ("breathing", "hard_resting"): "breathing is hard even at rest",
    ("swelling", "more"): "more swelling than yesterday",
    ("medicine", "dizzy"): "dizzy or light-headed after medicines",
    ("medicine", "rash"): "rash or itching after medicines",
    ("medicine", "stomach"): "upset stomach after medicines",
}

STATUS = ["green", "amber", "red"]


def evaluate(breathing: str, swelling: str, medicine: str) -> tuple[str, list[str]]:
    """Return (status, reasons). Status is the worst single answer."""
    scored = [
        ("breathing", breathing, BREATHING[breathing]),
        ("swelling", swelling, SWELLING[swelling]),
        ("medicine", medicine, MEDICINE[medicine]),
    ]
    level = max(score for _, _, score in scored)
    reasons = [PHRASES[(q, a)] for q, a, score in scored if score > 0 and (q, a) in PHRASES]
    return STATUS[level], reasons
