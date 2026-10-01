import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import case_for_user
from ..models import Case, OtpCode, User
from ..notify import Notifier, get_notifier
from ..schemas import OtpRequest, TokenOut, VerifyIn
from ..security import code_matches, create_token, hash_code, new_otp, normalize_email, normalize_phone
from ..timeutil import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("medsure.auth")


def _norm(phone: str, email: str) -> tuple[str, str]:
    try:
        p = normalize_phone(phone)
    except ValueError:
        raise HTTPException(422, "Enter a valid mobile number")
    e = normalize_email(email)
    if "@" not in e or "." not in e.split("@")[-1]:
        raise HTTPException(422, "Enter a valid email address")
    return p, e


@router.post("/request-otp")
def request_otp(body: OtpRequest, db: Session = Depends(get_db), notifier: Notifier = Depends(get_notifier)):
    """Sends one 6-digit code by SMS and a different one by email. Both must be entered to sign in."""
    phone, email = _norm(body.phone, body.email)
    # Throttle: at most 5 codes per number per 10 minutes.
    recent = db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.expires_at > utcnow() - timedelta(minutes=5))).all()
    if len(recent) >= 5:
        raise HTTPException(429, "Too many codes requested. Try again in a few minutes.")
    code_p, code_e = new_otp(), new_otp()
    db.add(OtpCode(phone=phone, email=email, phone_hash=hash_code(code_p), email_hash=hash_code(code_e),
                   expires_at=utcnow() + timedelta(seconds=settings.otp_ttl_seconds)))
    db.commit()
    if settings.dev_mode:
        log.warning("DEV OTPs for %s / %s -> sms=%s email=%s%s", phone, email, code_p, code_e,
                    f"  (DEV_OTP {settings.dev_otp} also works)" if settings.dev_otp else "")
    try:
        notifier.sms(phone, f"Your MedSure code is {code_p}. It expires in {settings.otp_ttl_seconds // 60} minutes.")
        notifier.email(email, "Your MedSure code", f"Your MedSure code is {code_e}. It expires in {settings.otp_ttl_seconds // 60} minutes.")
    except Exception:
        log.exception("could not deliver OTP")
        if not settings.dev_mode:
            raise HTTPException(503, "Could not send the codes. Please try again.")
        # DEV_MODE: the codes are in the server log (and DEV_OTP works), so carry on.
        log.warning("DEV_MODE: continuing although the OTP could not be delivered")
    return {"sent": True, "expires_in": settings.otp_ttl_seconds}


@router.post("/verify", response_model=TokenOut)
def verify(body: VerifyIn, db: Session = Depends(get_db)):
    phone, email = _norm(body.phone, body.email)
    otp = db.scalar(select(OtpCode).where(OtpCode.phone == phone, OtpCode.email == email, OtpCode.used.is_(False))
                    .order_by(OtpCode.id.desc()))
    if otp is None or otp.expires_at < utcnow():
        raise HTTPException(400, "Codes expired. Request new ones.")
    if otp.attempts >= settings.otp_max_attempts:
        raise HTTPException(429, "Too many wrong attempts. Request new codes.")
    if not (code_matches(body.otp_phone, otp.phone_hash) and code_matches(body.otp_email, otp.email_hash)):
        otp.attempts += 1
        db.commit()
        raise HTTPException(400, "The codes don't match")
    otp.used = True

    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        if body.role == "family":
            raise HTTPException(404, "No invitation found for this number. Ask the patient to add you.")
        user = User(name=(body.name or "Patient").strip(), phone=phone, email=email, role="patient", language=body.language)
        db.add(user)
        db.flush()
        db.add(Case(patient_id=user.id))
    else:
        if user.email != email:
            raise HTTPException(400, "This number is registered with a different email")
        if user.role != body.role:
            raise HTTPException(400, f"This number is registered as {user.role}")
        if body.name and user.role == "patient":
            user.name = body.name.strip()
    db.flush()
    case = case_for_user(db, user)
    db.commit()
    return TokenOut(token=create_token(user.id), role=user.role, user_id=user.id, case_id=case.id)