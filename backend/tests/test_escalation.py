import threading
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, engine
from app.escalation import run_due
from app.models import Alert, AlertAttempt, AuditEvent, Device
from app.timeutil import utcnow

RED = {"breathing": "hard_resting", "swelling": "none", "medicine": "none"}
AMBER = {"breathing": "harder", "swelling": "none", "medicine": "none"}
GREEN = {"breathing": "normal", "swelling": "none", "medicine": "none"}


def called(fake):
    return [c[0] for c in fake.calls]


def red(client, f):
    r = client.post("/checkins", headers=f["pat"], json=RED)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "red"
    return r.json()["alert_id"]


def tokens(fake):
    return sorted(t for t, _ in fake.pushes)


def test_green_creates_no_alert_and_notifies_nobody(client, fake, family_setup):
    r = client.post("/checkins", headers=family_setup["pat"], json=GREEN).json()
    assert r["status"] == "green" and r["alert_id"] is None
    assert fake.pushes == [] and fake.calls == []


def test_amber_pushes_everyone_but_never_calls(client, fake, family_setup):
    r = client.post("/checkins", headers=family_setup["pat"], json=AMBER).json()
    assert r["status"] == "amber" and r["alert_id"]
    assert tokens(fake) == ["tok-arjun-0000000", "tok-meera-0000000", "tok-ravi-00000000"]
    assert fake.calls == [] and fake.sms_sent == []


def test_note_never_changes_the_status(client, fake, family_setup):
    r = client.post("/checkins", headers=family_setup["pat"], json={**GREEN, "note": "chest pain, very bad"}).json()
    assert r["status"] == "green"   # fixed rules decide, not free text


def test_red_calls_first_approver_immediately(client, fake, family_setup):
    red(client, family_setup)
    assert called(fake) == ["+919876500002"]                       # Arjun only
    assert "tok-arjun-0000000" in tokens(fake)                      # he also gets the push
    assert "tok-ravi-00000000" in tokens(fake)                      # view-only gets an info push
    assert "tok-meera-0000000" not in tokens(fake)                  # Meera isn't contacted yet
    assert all(d["type"] == "red_alert" and d["patient"] == "Lakshmi" for _, d in fake.pushes)


def test_voice_url_points_at_this_alert_and_member(client, fake, family_setup):
    aid = red(client, family_setup)
    to, voice_url, status_url = fake.calls[0]
    uid = family_setup["ids"]["arjun"]
    assert voice_url == f"https://example.test/twilio/voice/{aid}/{uid}"
    assert status_url == f"https://example.test/twilio/status/{aid}/{uid}"


def test_full_escalation_timeline(client, fake, family_setup, db):
    red(client, family_setup)
    t0 = utcnow()
    assert run_due(db, fake, now=t0 + timedelta(seconds=30)) == 0            # still waiting for Arjun
    assert called(fake) == ["+919876500002"]

    assert run_due(db, fake, now=t0 + timedelta(seconds=61)) == 1            # Arjun didn't answer -> Meera
    assert called(fake) == ["+919876500002", "+919876500003"]

    assert run_due(db, fake, now=t0 + timedelta(seconds=125)) == 1           # nobody -> broadcast
    assert called(fake)[2:] == ["+919876500002", "+919876500003"]            # both approvers again
    assert sorted(to for to, _ in fake.sms_sent) == ["+919876500002", "+919876500003", "+919876500004"]  # SMS whole circle
    assert "+919876500004" not in called(fake)                               # view-only is NEVER phoned

    assert run_due(db, fake, now=t0 + timedelta(seconds=190)) == 1
    alert = db.scalars(select(Alert)).one()
    assert alert.status == "exhausted" and alert.next_run_at is None
    assert run_due(db, fake, now=t0 + timedelta(seconds=999)) == 0           # finished; nothing more happens
    actions = [e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.alert_id == alert.id).order_by(AuditEvent.id))]
    assert actions[:2] == ["red_alert_created", "escalation_started"] and actions[-1] == "exhausted"


def test_ack_in_app_stops_escalation_and_tells_the_others(client, fake, family_setup, db):
    f = family_setup
    aid = red(client, f)
    fake.pushes.clear()
    r = client.post(f"/alerts/{aid}/ack", headers=f["arjun"])
    assert r.status_code == 200 and r.json()["status"] == "acknowledged" and r.json()["acknowledged_via"] == "app"
    assert {d["type"] for _, d in fake.pushes} == {"alert_ack"}
    assert tokens(fake) == ["tok-meera-0000000", "tok-ravi-00000000"]       # not back to Arjun
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=500)) == 0
    assert called(fake) == ["+919876500002"]                                  # Meera never called


def test_view_only_member_cannot_acknowledge(client, fake, family_setup):
    f = family_setup
    aid = red(client, f)
    assert client.post(f"/alerts/{aid}/ack", headers=f["ravi"]).status_code == 403
    assert client.post(f"/alerts/{aid}/ack", headers=f["pat"]).status_code == 403


def test_press_1_on_the_call_acknowledges(client, fake, family_setup):
    f = family_setup
    aid = red(client, f)
    uid = f["ids"]["arjun"]
    wrong = client.post(f"/twilio/ack/{aid}/{uid}", data={"Digits": "5"})
    assert wrong.status_code == 200 and "<Gather" in wrong.text                # asks again
    assert client.get(f"/alerts/{aid}", headers=f["arjun"]).json()["status"] == "open"
    ok = client.post(f"/twilio/ack/{aid}/{uid}", data={"Digits": "1"})
    assert ok.status_code == 200 and "<Gather" not in ok.text
    a = client.get(f"/alerts/{aid}", headers=f["arjun"]).json()
    assert a["status"] == "acknowledged" and a["acknowledged_via"] == "call" and a["acknowledged_by"] == uid


def test_view_only_member_pressing_1_does_not_acknowledge(client, fake, family_setup):
    f = family_setup
    aid = red(client, f)
    client.post(f"/twilio/ack/{aid}/{f['ids']['ravi']}", data={"Digits": "1"})
    assert client.get(f"/alerts/{aid}", headers=f["arjun"]).json()["status"] == "open"


def test_unanswered_call_moves_on_without_waiting(client, fake, family_setup, db):
    f = family_setup
    aid = red(client, f)
    sid = db.scalars(select(AlertAttempt).where(AlertAttempt.channel == "call")).one().provider_ref
    r = client.post(f"/twilio/status/{aid}/{f['ids']['arjun']}", data={"CallSid": sid, "CallStatus": "no-answer"})
    assert r.status_code == 204
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=2)) == 1       # only 2 seconds later
    assert called(fake) == ["+919876500002", "+919876500003"]


def test_answered_call_without_pressing_1_still_waits_the_full_window(client, fake, family_setup, db):
    f = family_setup
    aid = red(client, f)
    sid = db.scalars(select(AlertAttempt).where(AlertAttempt.channel == "call")).one().provider_ref
    client.post(f"/twilio/status/{aid}/{f['ids']['arjun']}", data={"CallSid": sid, "CallStatus": "completed"})
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=10)) == 0


def test_member_who_turned_off_alert_calls_is_skipped(client, fake, family_setup):
    f = family_setup
    assert client.patch("/me/settings", headers=f["arjun"], json={"allow_alert_calls": False}).status_code == 200
    red(client, f)
    assert called(fake) == ["+919876500003"]                                  # straight to Meera


def test_nobody_callable_still_pushes_everyone_and_is_logged(client, fake, family_setup, db):
    f = family_setup
    for h in (f["arjun"], f["meera"]):
        client.patch("/me/settings", headers=h, json={"allow_alert_calls": False})
    red(client, f)
    assert fake.calls == []
    assert tokens(fake) == ["tok-arjun-0000000", "tok-meera-0000000", "tok-ravi-00000000"]
    assert db.scalars(select(Alert)).one().status == "exhausted"
    assert "no_callable_members" in [e.action for e in db.scalars(select(AuditEvent))]


def test_twilio_outage_does_not_stop_the_escalation(client, fake, family_setup, db):
    f = family_setup
    fake.fail_calls = True
    red(client, f)
    assert fake.calls == []
    failed = db.scalars(select(AlertAttempt).where(AlertAttempt.channel == "call")).one()
    assert failed.status == "failed" and "twilio down" in failed.detail
    assert "tok-arjun-0000000" in tokens(fake)                                # push still went out
    fake.fail_calls = False
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=61)) == 1       # next person is still tried
    assert called(fake) == ["+919876500003"]


def test_dead_push_token_is_deleted(client, fake, family_setup, db):
    f = family_setup
    fake.bad_tokens.add("tok-arjun-0000000")
    red(client, f)
    assert db.scalar(select(Device).where(Device.fcm_token == "tok-arjun-0000000")) is None
    assert called(fake) == ["+919876500002"]                                  # call still placed


def test_cancel_window(client, fake, family_setup, db, monkeypatch):
    f = family_setup
    monkeypatch.setattr(settings, "cancel_window_seconds", 30)
    aid = red(client, f)
    assert fake.calls == [] and fake.pushes == []                             # nothing yet: patient can still cancel
    assert client.post(f"/alerts/{aid}/cancel", headers=f["pat"]).status_code == 200
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=60)) == 0
    assert fake.calls == []


def test_cancel_window_expires_then_escalation_runs_and_cancel_is_too_late(client, fake, family_setup, db, monkeypatch):
    f = family_setup
    monkeypatch.setattr(settings, "cancel_window_seconds", 30)
    aid = red(client, f)
    assert run_due(db, fake, now=utcnow() + timedelta(seconds=31)) == 1
    assert called(fake) == ["+919876500002"]
    assert client.post(f"/alerts/{aid}/cancel", headers=f["pat"]).status_code == 409


def test_family_cannot_cancel(client, fake, family_setup, monkeypatch):
    f = family_setup
    monkeypatch.setattr(settings, "cancel_window_seconds", 30)
    aid = red(client, f)
    assert client.post(f"/alerts/{aid}/cancel", headers=f["arjun"]).status_code == 403


def test_alert_detail_shows_attempts_and_audit(client, fake, family_setup):
    f = family_setup
    aid = red(client, f)
    a = client.get(f"/alerts/{aid}", headers=f["arjun"]).json()
    assert {t["channel"] for t in a["attempts"]} == {"push", "call"}
    audit = client.get(f"/alerts/{aid}/audit", headers=f["arjun"]).json()
    assert [e["action"] for e in audit][:3] == ["red_alert_created", "escalation_started", "contacted"]


def test_voice_message_language_and_privacy(client, fake, family_setup):
    f = family_setup
    aid = red(client, f)
    en = client.post(f"/twilio/voice/{aid}/{f['ids']['arjun']}").text
    assert 'language="en-IN"' in en and "Lakshmi" in en and en.count("<Gather") == 2
    assert "breathing" not in en.lower()                                      # no medical detail is read aloud
    client.patch("/me/settings", headers=f["arjun"], json={"language": "ta"})
    ta = client.post(f"/twilio/voice/{aid}/{f['ids']['arjun']}").text
    assert 'language="ta-IN"' in ta


def test_twilio_signature_is_enforced(client, fake, family_setup, monkeypatch):
    from twilio.request_validator import RequestValidator

    f = family_setup
    aid = red(client, f)
    monkeypatch.setattr(settings, "twilio_auth_token", "secret-token")
    path = f"/twilio/ack/{aid}/{f['ids']['arjun']}"
    assert client.post(path, data={"Digits": "1"}).status_code == 403                  # unsigned: refused
    sig = RequestValidator("secret-token").compute_signature("https://example.test" + path, {"Digits": "1"})
    assert client.post(path, data={"Digits": "1"}, headers={"X-Twilio-Signature": sig}).status_code == 200


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locking needs PostgreSQL")
def test_concurrent_workers_never_double_call(client, fake, family_setup, monkeypatch):
    monkeypatch.setattr(settings, "cancel_window_seconds", 30)
    red(client, family_setup)
    due = utcnow() + timedelta(seconds=31)
    barrier = threading.Barrier(8)

    def worker():
        s = SessionLocal()
        barrier.wait()
        run_due(s, fake, now=due)
        s.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert called(fake) == ["+919876500002"]      # exactly one call, despite 8 workers racing
