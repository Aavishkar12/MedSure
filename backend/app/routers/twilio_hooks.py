"""Webhooks Twilio calls during an alert call. Every request is signature-checked."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from ..config import settings
from ..db import get_db
from ..escalation import acknowledge, record_call_result
from ..models import Alert, CaseMember, User
from ..notify import Notifier, get_notifier
from ..voice import alert_twiml, thanks_twiml

router = APIRouter(prefix="/twilio", tags=["twilio"])


async def verify_twilio(request: Request) -> dict:
    form = dict(await request.form())
    if settings.twilio_validate_signature and settings.twilio_auth_token:
        url = settings.base_url.rstrip("/") + request.url.path
        sig = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(settings.twilio_auth_token).validate(url, form, sig):
            raise HTTPException(403, "Bad Twilio signature")
    return form


def _load(db: Session, alert_id: str, user_id: int) -> tuple[Alert, User]:
    alert, user = db.get(Alert, alert_id), db.get(User, user_id)
    if alert is None or user is None:
        raise HTTPException(404, "Unknown alert or user")
    return alert, user


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


@router.post("/voice/{alert_id}/{user_id}")
async def voice(alert_id: str, user_id: int, db: Session = Depends(get_db), _form: dict = Depends(verify_twilio)):
    alert, user = _load(db, alert_id, user_id)
    ack = f"{settings.base_url.rstrip('/')}/twilio/ack/{alert.id}/{user.id}"
    return _xml(alert_twiml(alert.case.patient.name, user.language, ack))


@router.post("/ack/{alert_id}/{user_id}")
async def ack(alert_id: str, user_id: int, db: Session = Depends(get_db), form: dict = Depends(verify_twilio),
              notifier: Notifier = Depends(get_notifier)):
    alert, user = _load(db, alert_id, user_id)
    if form.get("Digits") == "1":
        member = db.scalar(select(CaseMember).where(CaseMember.case_id == alert.case_id, CaseMember.user_id == user.id))
        if member is not None and member.permission == "approve":
            acknowledge(db, alert, user.id, "call", notifier)
            db.commit()
            return _xml(thanks_twiml(user.language))
    # Any other key: ask again.
    ack_url = f"{settings.base_url.rstrip('/')}/twilio/ack/{alert.id}/{user.id}"
    return _xml(alert_twiml(alert.case.patient.name, user.language, ack_url))


@router.post("/status/{alert_id}/{user_id}")
async def status(alert_id: str, user_id: int, db: Session = Depends(get_db), form: dict = Depends(verify_twilio)):
    alert, _user = _load(db, alert_id, user_id)
    record_call_result(db, alert, user_id, form.get("CallSid", ""), form.get("CallStatus", ""))
    db.commit()
    return Response(status_code=204)
