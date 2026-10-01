from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from . import firebase
from .config import settings
from .db import get_session
from .models import Case, CaseMember, TimelineEvent, User


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

    user = session.get(User, uid)
    if not user:
        user = User(id=uid, name=name, email=email)
    elif (name and user.name != name) or (email and user.email != email):
        user.name, user.email = name or user.name, email or user.email
    else:
        return user
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def require_member(session: Session, case_id: int, user: User) -> Case:
    case = session.get(Case, case_id)
    if not case or not session.get(CaseMember, (case_id, user.id)):
        raise HTTPException(404, "Case not found")
    return case


def add_event(session: Session, case_id: int, kind: str, title: str, ref_id: int | None = None) -> None:
    session.add(TimelineEvent(case_id=case_id, kind=kind, title=title, ref_id=ref_id))
