import pytest

from app.rules import evaluate


@pytest.mark.parametrize("b,s,m,expected", [
    ("normal", "none", "none", "green"),
    ("normal", "same", "none", "green"),
    ("harder", "none", "none", "amber"),
    ("normal", "more", "none", "amber"),
    ("normal", "none", "dizzy", "amber"),
    ("normal", "none", "rash", "amber"),
    ("hard_resting", "none", "none", "red"),
    ("hard_resting", "more", "dizzy", "red"),
])
def test_status_is_worst_answer(b, s, m, expected):
    assert evaluate(b, s, m)[0] == expected


def test_reasons_listed_for_non_clear_answers():
    status, reasons = evaluate("hard_resting", "more", "none")
    assert status == "red"
    assert "breathing is hard even at rest" in reasons and "more swelling than yesterday" in reasons
