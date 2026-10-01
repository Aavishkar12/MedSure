import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import case_for_user
from ..escalation import run_due, start_alert
from ..models import Checkin, User
from ..notify import Notifier, get_notifier
from ..rules import evaluate
from ..schemas import CheckinIn, CheckinOut
from ..security import current_user

router = APIRouter(tags=["checkins"])
log = logging.getLogger("medsure.checkins")


def dispatch_now() -> None:
    """Run the escalation step immediately so the first call isn't delayed by the worker's poll interval."""
    db = SessionLocal()
    try:
        run_due(db, get_notifier())
    except Exception:
        log.exception("immediate dispatch failed; the worker will retry")
    finally:
        db.close()


@router.post("/checkins", response_model=CheckinOut)
def submit_checkin(body: CheckinIn, background: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(current_user), notifier: Notifier = Depends(get_notifier)):
    if user.role != "patient":
        raise HTTPException(403, "Only the patient submits check-ins")
    case = case_for_user(db, user)
    status, reasons = evaluate(body.breathing, body.swelling, body.medicine)
    checkin = Checkin(case_id=case.id, answers=body.model_dump(exclude={"note"}), note=body.note, status=status, reasons=reasons)
    db.add(checkin)
    db.flush()
    summary = "; ".join(reasons) if reasons else "all clear"
    alert = start_alert(db, case, checkin, status, summary, notifier)
    db.commit()
    if alert is not None and alert.level == "red" and settings.cancel_window_seconds == 0:
        background.add_task(dispatch_now)
    return CheckinOut(checkin_id=checkin.id, status=status, reasons=reasons,
                      alert_id=alert.id if alert else None,
                      cancel_window_seconds=settings.cancel_window_seconds if status == "red" else 0)
