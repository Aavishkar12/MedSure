from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import alert_for_user, case_for_user, membership
from ..escalation import acknowledge, cancel
from ..models import Alert, AlertAttempt, AuditEvent, User
from ..notify import Notifier, get_notifier
from ..schemas import AlertOut, AttemptOut
from ..security import current_user

router = APIRouter(tags=["alerts"])


def _out(db: Session, a: Alert) -> AlertOut:
    attempts = db.scalars(select(AlertAttempt).where(AlertAttempt.alert_id == a.id).order_by(AlertAttempt.id))
    return AlertOut(id=a.id, level=a.level, status=a.status, summary=a.summary, created_at=a.created_at,
                    acknowledged_at=a.acknowledged_at, acknowledged_by=a.acknowledged_by, acknowledged_via=a.acknowledged_via,
                    attempts=[AttemptOut(user_id=t.user_id, channel=t.channel, status=t.status, created_at=t.created_at) for t in attempts])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    case = case_for_user(db, user)
    rows = db.scalars(select(Alert).where(Alert.case_id == case.id).order_by(Alert.created_at.desc()).limit(50))
    return [_out(db, a) for a in rows]


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert: Alert = Depends(alert_for_user), db: Session = Depends(get_db)):
    return _out(db, alert)


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert: Alert = Depends(alert_for_user), db: Session = Depends(get_db),
              user: User = Depends(current_user), notifier: Notifier = Depends(get_notifier)):
    """Family taps 'I'm on it' in the app (or on the notification). Same effect as pressing 1 on the call."""
    if user.role != "family":
        raise HTTPException(403, "Only family members acknowledge alerts")
    m = membership(db, alert.case, user)
    if m is None or m.permission != "approve":
        raise HTTPException(403, "Only family members who can approve may acknowledge")
    acknowledge(db, alert, user.id, "app", notifier)
    db.commit()
    return _out(db, alert)


@router.post("/alerts/{alert_id}/cancel")
def cancel_alert(alert: Alert = Depends(alert_for_user), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Patient taps 'I tapped by mistake' during the optional cancel window."""
    if user.role != "patient":
        raise HTTPException(403, "Only the patient can cancel")
    if not cancel(db, alert, user.id):
        raise HTTPException(409, "Too late to cancel. Family have already been contacted.")
    db.commit()
    return {"cancelled": True}


@router.get("/alerts/{alert_id}/audit")
def alert_audit(alert: Alert = Depends(alert_for_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.alert_id == alert.id).order_by(AuditEvent.id))
    return [{"at": r.at, "actor": r.actor, "action": r.action, "detail": r.detail} for r in rows]
