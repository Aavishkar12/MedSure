from fastapi import Depends, Header, HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from . import firebase
from .config import settings
from .db import get_session
from .models import Case, CaseMember, Device, Invite, TimelineEvent, User


def current_user(
    authorization: str | None = Header(None, description="Bearer <Firebase ID token>"),
    x_user_id: str | None = Header(None, description="Dev only, when AUTH_DEV_BYPASS=true"),
    session: Session = Depends(get_session),
) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        if not firebase.enabled():
            raise HTTPException(503, "Firebase is not configured on the server")
        try:
            claims = firebase.verify_token(authorization[7:].strip())
        except Exception:
            raise HTTPException(401, "Invalid or expired sign-in token")
        uid, name, email = claims["uid"], claims.get("name") or "", claims.get("email")
    elif settings.auth_dev_bypass and x_user_id:
        uid, name, email = x_user_id, "", None
    else:
        raise HTTPException(401, "Sign in required")

    email = clean_email(email)
    user = session.get(User, uid)
    if not user:
        user = User(id=uid, name=name, email=email)
    elif (name and not user.name) or (email and user.email != email):
        user.name, user.email = user.name or name, email or user.email
    else:
        return user
    session.add(user)
    claim_invites(session, user)
    session.commit()
    session.refresh(user)
    return user


def clean_phone(value: str | None) -> str | None:
    digits = "".join(ch for ch in value or "" if ch.isdigit())
    return digits[-10:] or None


def clean_email(value: str | None) -> str | None:
    return (value or "").strip().lower() or None


def claim_invites(session: Session, user: User) -> None:
    """Turn invites addressed to this user's phone or email into memberships. Caller commits."""
    matches = [Invite.phone == user.phone] if user.phone else []
    matches += [Invite.email == user.email] if user.email else []
    if not matches:
        return
    for invite in session.exec(select(Invite).where(or_(*matches))).all():
        if not session.get(CaseMember, (invite.case_id, user.id)):
            session.add(
                CaseMember(case_id=invite.case_id, user_id=user.id, relation=invite.relation, can_approve=invite.can_approve)
            )
        user.name = user.name or invite.name
        session.delete(invite)


def adopt_phone(session: Session, user: User) -> None:
    """A phone number identifies a person. Signing in again creates a new account, so whatever
    older accounts with this number belonged to moves to the current one. Caller commits.

    Without this, an invite sent to that number lands on a stale account whose phone never hears about it.
    """
    if not user.phone:
        return
    for old in session.exec(select(User).where(User.phone == user.phone, User.id != user.id)).all():
        for m in session.exec(select(CaseMember).where(CaseMember.user_id == old.id)).all():
            mine = session.get(CaseMember, (m.case_id, user.id))
            if mine:
                mine.can_approve = mine.can_approve or m.can_approve
                session.add(mine)
            else:
                session.add(CaseMember(case_id=m.case_id, user_id=user.id, relation=m.relation, can_approve=m.can_approve))
            session.delete(m)
        for device in session.exec(select(Device).where(Device.user_id == old.id)).all():
            device.user_id = user.id  # a phone still registered under the old account keeps getting alerts
            session.add(device)
        user.name = user.name or old.name
        old.phone = None
        session.add(old)


def require_member(session: Session, case_id: int, user: User) -> Case:
    case = session.get(Case, case_id)
    if not case or not session.get(CaseMember, (case_id, user.id)):
        raise HTTPException(404, "Case not found")
    return case


def add_event(session: Session, case_id: int, kind: str, title: str, ref_id: int | None = None) -> None:
    session.add(TimelineEvent(case_id=case_id, kind=kind, title=title, ref_id=ref_id))
