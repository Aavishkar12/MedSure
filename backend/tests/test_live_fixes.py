"""Behaviours found by running the real model: per-day limits, rate limits, bill quantities."""
import json
from unittest.mock import MagicMock, patch

import pytest
from groq import RateLimitError

from app import llm
from app.llm import client
from app.routers.documents import _with_quantity

POLICY = {"room_rent_limit_per_day": 4000.0, "copay_percent": 10.0, "sum_insured": 300000.0}


def test_room_rent_limit_is_per_day_whatever_the_model_says():
    bill = [
        {"id": 1, "description": "Room rent - single AC room (5 x Rs 6000)", "amount": 30000.0},
        {"id": 2, "description": "Operation theatre charges", "amount": 18000.0},
    ]
    # The real model answered 4,000 for the whole stay: it applied the daily limit once.
    reply = {"items": [
        {"bill_item_id": 1, "status": "partly_covered", "claimable_amount": 4000, "reason": "Capped."},
        {"bill_item_id": 2, "status": "covered", "claimable_amount": 18000, "reason": "Covered."},
    ]}
    with patch("app.llm.client._chat", return_value=json.dumps(reply)):
        report = llm.compare_bill_to_policy(bill, POLICY, "")
    room = report["items"][0]
    assert room["status"] == "partly_covered"
    assert room["claimable_amount"] == 20000  # 5 days x Rs 4,000
    assert "Rs 4,000 a day" in room["reason"] and "Rs 20,000" in room["reason"]
    assert report["totals"]["eligible"] == 38000
    assert report["totals"]["estimated_claimable"] == 34200  # less the 10% co-payment


def test_room_within_limit_and_other_rooms_are_left_to_the_model():
    bill = [
        {"id": 1, "description": "Room rent - general ward (3 x Rs 2500)", "amount": 7500.0},
        {"id": 2, "description": "ICU charges (2 x Rs 9000)", "amount": 18000.0},
    ]
    reply = {"items": [
        {"bill_item_id": 1, "status": "covered", "claimable_amount": 7500, "reason": "Within the limit."},
        {"bill_item_id": 2, "status": "covered", "claimable_amount": 18000, "reason": "ICU is covered."},
    ]}
    with patch("app.llm.client._chat", return_value=json.dumps(reply)):
        report = llm.compare_bill_to_policy(bill, POLICY, "")
    assert [i["claimable_amount"] for i in report["items"]] == [7500, 18000]


def test_quantity_is_kept_with_the_bill_line():
    assert _with_quantity("Room rent", 5, 6000) == "Room rent (5 x Rs 6000)"
    assert _with_quantity("Surgeon fee", 1, 45000) == "Surgeon fee"
    assert _with_quantity("Room rent", None, None) == "Room rent"
    assert _with_quantity("Room rent (5 x Rs 6000)", 5, 6000) == "Room rent (5 x Rs 6000)"


def _rate_limited(retry_after="2"):
    response = MagicMock(status_code=429, headers={"retry-after": retry_after})
    return RateLimitError("rate limit", response=response, body=None)


def test_rate_limit_waits_and_retries():
    calls = [_rate_limited("2"), _rate_limited("3"), "{\"ok\": true}"]

    def fake_once(**kwargs):
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(client, "_chat_once", side_effect=fake_once), patch.object(client.time, "sleep") as sleep:
        assert client._chat(model="m", messages=[]) == "{\"ok\": true}"
    assert [c.args[0] for c in sleep.call_args_list] == [2.0, 3.0]


def test_rate_limit_gives_up_with_a_message_for_the_user():
    with patch.object(client, "_chat_once", side_effect=lambda **k: (_ for _ in ()).throw(_rate_limited("999"))), \
         patch.object(client.time, "sleep") as sleep:
        with pytest.raises(llm.LLMError, match="busy"):
            client._chat(model="m", messages=[])
    assert sleep.call_count == client.RATE_LIMIT_ATTEMPTS - 1
    assert all(c.args[0] == client.RATE_LIMIT_MAX_WAIT for c in sleep.call_args_list)  # capped
