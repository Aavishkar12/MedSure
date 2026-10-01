"""Red-alert escalation.

State lives in the database (alerts.current_idx / alerts.next_run_at), so a server restart can't lose
an alert half-way through. A worker calls run_due() every couple of seconds.

Sequence for a RED alert (callers = approvers who allow alert calls, ordered by priority):
  step 0..n-1 : push + phone call to caller #i, then wait ACK_WINDOW seconds
  step n      : broadcast. Call every caller again and SMS the whole circle, then wait once more
  step n+1    : nobody acknowledged -> status "exhausted" (logged, visible in the app)
Anyone acknowledging (pressing 1 on the call, or tapping Acknowledge in the app) stops it at once.
"""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Alert, AlertAttempt, AuditEvent, Case, CaseMember, Checkin, Device
from .notify import InvalidPushToken, Notifier
from .timeutil import utcnow

log = logging.getLogger("medsure.escalation")

# Terminal call results that mean "this person did not pick up", so move on immediately.
UNANSWERED = {"busy", "no-answer", "failed", "canceled"}


def audit(db: Session, case_id: int, alert_id: str | None, actor: str, action: str, **detail) -> None:
    db.add(AuditEvent(case_id=case_id, alert_id=alert_id, actor=actor, action=action, detail=detail))


def _members(db: Session, case_id: int) -> list[CaseMember]:
    return list(db.scalars(
        select(CaseMember).where(CaseMember.case_id == case_id).order_by(CaseMember.priority, CaseMember.id)
    ))


def callers_of(members: list[CaseMember]) -> list[CaseMember]:
    """Only people who may approve AND consented to alert calls get phoned. View-only members never do."""
    return [m for m in members if m.permission == "approve" and m.allow_alert_calls]


def _record(db: Session, alert: Alert, user_id: int, channel: str, status: str, ref: str | None = None, detail: str | None = None):
    db.add(AlertAttempt(alert_id=alert.id, user_id=user_id, channel=channel, status=status, provider_ref=ref, detail=detail))


def _push(db: Session, alert: Alert, member: CaseMember, notifier: Notifier, kind: str = "red_alert") -> None:
    """Push to every device of one member. A failing device never stops the escalation."""
    patient = alert.case.patient.name
    data = {"type": kind, "alert_id": alert.id, "level": alert.level, "patient": patient}
    for dev in list(db.scalars(select(Device).where(Device.user_id == member.user_id))):
        try:
            ref = notifier.push(dev.fcm_token, data)
            _record(db, alert, member.user_id, "push", "sent", ref)
        except InvalidPushToken as e:
            db.delete(dev)
            _record(db, alert, member.user_id, "push", "invalid_token", detail=str(e))
        except Exception as e:
            log.exception("push failed")
            _record(db, alert, member.user_id, "push", "failed", detail=str(e)[:300])


def _call(db: Session, alert: Alert, member: CaseMember, notifier: Notifier) -> None:
    base = settings.base_url.rstrip("/")
    voice = f"{base}/twilio/voice/{alert.id}/{member.user_id}"
    status = f"{base}/twilio/status/{alert.id}/{member.user_id}"
    try:
        ref = notifier.call(member.user.phone, voice, status)
        _record(db, alert, member.user_id, "call", "initiated", ref)
    except Exception as e:
        log.exception("call failed")
        _record(db, alert, member.user_id, "call", "failed", detail=str(e)[:300])


def _sms(db: Session, alert: Alert, member: CaseMember, notifier: Notifier) -> None:
    text = (f"MedSure URGENT: {alert.case.patient.name}'s check-in shows a RED alert. "
            f"Please call them now, or call 108 if you cannot reach them. Open MedSure for details.")
    try:
        ref = notifier.sms(member.user.phone, text)
        _record(db, alert, member.user_id, "sms", "sent", ref)
    except Exception as e:
        log.exception("sms failed")
        _record(db, alert, member.user_id, "sms", "failed", detail=str(e)[:300])


# ---------------------------------------------------------------- creating alerts

def start_alert(db: Session, case: Case, checkin: Checkin, level: str, summary: str, notifier: Notifier) -> Alert | None:
    """Called right after a check-in is saved. Green does nothing. Amber pushes only. Red starts escalation."""
    if level == "green":
        return None
    now = utcnow()
    alert = Alert(case_id=case.id, checkin_id=checkin.id, level=level, summary=summary)
    alert.case = case
    db.add(alert)
    db.flush()
    members = _members(db, case.id)

    if level == "amber":
        alert.status = "notified"
        alert.dispatched_at = now
        for m in members:
            _push(db, alert, m, notifier, kind="amber_alert")
        audit(db, case.id, alert.id, "system", "amber_pushed", members=len(members))
        return alert

    alert.status = "open"
    alert.next_run_at = now + timedelta(seconds=settings.cancel_window_seconds)
    audit(db, case.id, alert.id, "system", "red_alert_created", summary=summary,
          cancel_window=settings.cancel_window_seconds)
    return alert


# ---------------------------------------------------------------- the worker step

def run_due(db: Session, notifier: Notifier, now=None, limit: int = 20) -> int:
    """Process every open alert whose timer has expired. Safe to run from several workers at once."""
    now = now or utcnow()
    ids = list(db.scalars(
        select(Alert.id).where(Alert.status == "open", Alert.next_run_at <= now).order_by(Alert.next_run_at).limit(limit)
    ))
    done = 0
    for aid in ids:
        # Lock the row; if another worker already holds it, skip. (SQLite ignores FOR UPDATE.)
        alert = db.scalar(
            select(Alert).where(Alert.id == aid, Alert.status == "open", Alert.next_run_at <= now)
            .with_for_update(skip_locked=True)
        )
        if alert is None:
            continue
        _step(db, alert, notifier, now)
        db.commit()
        done += 1
    return done


def _step(db: Session, alert: Alert, notifier: Notifier, now) -> None:
    window = timedelta(seconds=settings.ack_window_seconds)
    members = _members(db, alert.case_id)
    callers = callers_of(members)
    first = alert.dispatched_at is None
    if first:
        alert.dispatched_at = now
        audit(db, alert.case_id, alert.id, "system", "escalation_started", callers=len(callers))

    if not callers:
        # Nobody may be phoned. Push everyone and stop. This is visible in the audit trail.
        for m in members:
            _push(db, alert, m, notifier)
        alert.status, alert.next_run_at = "exhausted", None
        audit(db, alert.case_id, alert.id, "system", "no_callable_members")
        return

    idx = alert.current_idx
    if idx < len(callers):
        m = callers[idx]
        if first:  # view-only members and non-callers get one informational push at the start
            for other in members:
                if other not in callers:
                    _push(db, alert, other, notifier)
        _push(db, alert, m, notifier)
        _call(db, alert, m, notifier)
        alert.current_idx = idx + 1
        alert.next_run_at = now + window
        audit(db, alert.case_id, alert.id, "system", "contacted", user_id=m.user_id, position=idx + 1, of=len(callers))
    elif idx == len(callers):
        for m in callers:
            _push(db, alert, m, notifier)
            _call(db, alert, m, notifier)
        for m in members:
            _sms(db, alert, m, notifier)
        alert.current_idx = idx + 1
        alert.next_run_at = now + window
        audit(db, alert.case_id, alert.id, "system", "broadcast", callers=len(callers), sms=len(members))
    else:
        alert.status, alert.next_run_at = "exhausted", None
        audit(db, alert.case_id, alert.id, "system", "exhausted")


# ---------------------------------------------------------------- acknowledge / cancel / call results

def acknowledge(db: Session, alert: Alert, user_id: int, via: str, notifier: Notifier | None = None) -> Alert:
    """Stops escalation. Idempotent: the first acknowledgement wins."""
    if alert.status in ("acknowledged", "cancelled"):
        return alert
    alert.status, alert.next_run_at = "acknowledged", None
    alert.acknowledged_at, alert.acknowledged_by, alert.acknowledged_via = utcnow(), user_id, via
    audit(db, alert.case_id, alert.id, f"user:{user_id}", "acknowledged", via=via)
    if notifier is not None:  # tell the others so they don't all rush in
        for m in _members(db, alert.case_id):
            if m.user_id != user_id:
                _push(db, alert, m, notifier, kind="alert_ack")
    return alert


def cancel(db: Session, alert: Alert, user_id: int) -> bool:
    """Patient says 'tapped by mistake'. Only possible before the first call/push went out."""
    if alert.status != "open" or alert.dispatched_at is not None:
        return False
    alert.status, alert.next_run_at = "cancelled", None
    audit(db, alert.case_id, alert.id, f"user:{user_id}", "cancelled_by_patient")
    return True


def record_call_result(db: Session, alert: Alert, user_id: int, call_sid: str, call_status: str) -> None:
    """Twilio status callback. If the person didn't pick up, don't wait out the whole window."""
    attempt = db.scalar(select(AlertAttempt).where(AlertAttempt.provider_ref == call_sid, AlertAttempt.channel == "call"))
    if attempt:
        attempt.status = call_status
    audit(db, alert.case_id, alert.id, "twilio", "call_result", user_id=user_id, status=call_status)
    if alert.status != "open" or call_status not in UNANSWERED:
        return
    callers = callers_of(_members(db, alert.case_id))
    # Only speed up during the one-by-one phase, and only for the person currently being called.
    if 1 <= alert.current_idx <= len(callers) and callers[alert.current_idx - 1].user_id == user_id:
        alert.next_run_at = utcnow()
