from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Alert, Case, CaseMember, User
from .security import current_user


def case_for_user(db: Session, user: User) -> Case:
    """The patient's own case, or the case a family member belongs to."""
    if user.role == "patient":
        case = db.scalar(select(Case).where(Case.patient_id == user.id))
    else:
        case = db.scalar(select(Case).join(CaseMember).where(CaseMember.user_id == user.id))
    if case is None:
        raise HTTPException(404, "No case found for this user")
    return case


def membership(db: Session, case: Case, user: User) -> CaseMember | None:
    return db.scalar(select(CaseMember).where(CaseMember.case_id == case.id, CaseMember.user_id == user.id))


def alert_for_user(alert_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    case = alert.case
    if case.patient_id != user.id and membership(db, case, user) is None:
        raise HTTPException(403, "Not part of this case")
    return alert
