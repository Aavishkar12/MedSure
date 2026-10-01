from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import rules
from ..db import get_session
from ..deps import add_event, current_user, require_member
from ..models import Checkin, DischargeCard, User
from ..notify import notify_case

router = APIRouter(tags=["checkins"])


class CheckinCreate(BaseModel):
    answers: dict  # e.g. {"pain": 4, "fever": false, "temperature_c": 37.2, "notes": "..."}


@router.post("/cases/{case_id}/checkins", response_model=Checkin, status_code=201)
def create_checkin(
    case_id: int, body: CheckinCreate, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    require_member(session, case_id, user)
    card = session.exec(
        select(DischargeCard).where(DischargeCard.case_id == case_id).order_by(DischargeCard.id.desc())
    ).first()
    flags = rules.evaluate(body.answers, card.data if card else None)
    checkin = Checkin(case_id=case_id, answers=body.answers, flags=flags)
    session.add(checkin)
    session.flush()
    title = "Daily check-in: needs attention" if flags else "Daily check-in"
    add_event(session, case_id, "checkin", title, checkin.id)
    session.commit()
    session.refresh(checkin)
    if flags:
        urgent = any(f.get("severity") == "urgent" for f in flags)
        body = "Today's check-in needs help now." if urgent else "Today's check-in needs attention."
        # call_phone lets the family's notification offer a "Call" button for whoever checked in.
        extra = {"severity": "urgent" if urgent else "attention", "call_name": user.name, "call_phone": user.phone or ""}
        notify_case(session, case_id, "MedSure", body, "checkin", checkin.id, exclude_user_id=user.id, extra=extra)
    else:
        _silent_update(session, checkin, user)
    return checkin


def _silent_update(session: Session, checkin: Checkin, user: User) -> None:
    """Tell the rest of the family's phones to refresh, without showing a notification."""
    notify_case(session, checkin.case_id, "", "", "checkin", checkin.id, exclude_user_id=user.id)


class CheckinNote(BaseModel):
    note: str


@router.patch("/checkins/{checkin_id}", response_model=Checkin)
def update_checkin_note(
    checkin_id: int, body: CheckinNote, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    """Add or change the free-text note on a check-in. The note never affects the flags."""
    checkin = session.get(Checkin, checkin_id)
    if not checkin:
        raise HTTPException(404, "Check-in not found")
    require_member(session, checkin.case_id, user)
    checkin.answers = {**checkin.answers, "note": body.note.strip()[:500]}
    session.add(checkin)
    session.commit()
    session.refresh(checkin)
    _silent_update(session, checkin, user)
    return checkin


@router.get("/cases/{case_id}/checkins", response_model=list[Checkin])
def list_checkins(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    return session.exec(select(Checkin).where(Checkin.case_id == case_id).order_by(Checkin.created_at)).all()
