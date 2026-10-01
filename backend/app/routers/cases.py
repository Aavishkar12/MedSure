from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select

from ..db import get_session
from ..deps import add_event, clean_email, clean_phone, current_user, require_member
from ..models import Case, CaseMember, Invite, TimelineEvent, User

router = APIRouter(tags=["cases"])


class CaseCreate(BaseModel):
    patient_name: str
    relation: str = "self"  # "self" when the patient is the one signing up


class MemberInvite(BaseModel):
    name: str
    relation: str = "family"
    can_approve: bool = True
    phone: str | None = None
    email: str | None = None


class MemberOut(BaseModel):
    user_id: str | None  # None while the person has not signed in yet
    name: str
    relation: str
    can_approve: bool
    phone: str | None
    email: str | None
    pending: bool
    you: bool


@router.post("/cases", response_model=Case, status_code=201)
def create_case(body: CaseCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    case = Case(patient_name=body.patient_name, created_by=user.id)
    session.add(case)
    session.flush()
    session.add(CaseMember(case_id=case.id, user_id=user.id, relation=body.relation))
    session.commit()
    session.refresh(case)
    return case


@router.get("/cases", response_model=list[Case])
def list_cases(user: User = Depends(current_user), session: Session = Depends(get_session)):
    stmt = select(Case).join(CaseMember, CaseMember.case_id == Case.id).where(CaseMember.user_id == user.id)
    return session.exec(stmt).all()


@router.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return require_member(session, case_id, user)


@router.get("/cases/{case_id}/members", response_model=list[MemberOut])
def list_members(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    joined = session.exec(
        select(CaseMember, User).join(User, User.id == CaseMember.user_id).where(CaseMember.case_id == case_id)
    ).all()
    out = [
        MemberOut(
            user_id=u.id, name=u.name, relation=m.relation, can_approve=m.can_approve,
            phone=u.phone, email=u.email, pending=False, you=u.id == user.id,
        )
        for m, u in joined
    ]
    out.sort(key=lambda m: (m.relation != "self", m.name.lower()))  # patient first
    for i in session.exec(select(Invite).where(Invite.case_id == case_id)).all():
        out.append(
            MemberOut(
                user_id=None, name=i.name, relation=i.relation, can_approve=i.can_approve,
                phone=i.phone, email=i.email, pending=True, you=False,
            )
        )
    return out


@router.post("/cases/{case_id}/members", response_model=list[MemberOut], status_code=201)
def add_member(
    case_id: int, body: MemberInvite, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    """Add a family member by phone or email. They join straight away if they already have an account,
    otherwise as soon as they sign in with that phone or email."""
    require_member(session, case_id, user)
    phone, email = clean_phone(body.phone), clean_email(body.email)
    matches = ([User.phone == phone] if phone else []) + ([User.email == email] if email else [])
    existing = session.exec(select(User).where(or_(*matches))).first() if matches else None
    if existing:
        if not session.get(CaseMember, (case_id, existing.id)):
            session.add(
                CaseMember(case_id=case_id, user_id=existing.id, relation=body.relation, can_approve=body.can_approve)
            )
    else:
        session.add(
            Invite(
                case_id=case_id, name=body.name.strip(), relation=body.relation, can_approve=body.can_approve,
                phone=phone, email=email, invited_by=user.id,
            )
        )
    add_event(session, case_id, "member", f"{body.name.strip()} added to the family circle")
    session.commit()
    return list_members(case_id, user, session)


@router.get("/cases/{case_id}/timeline", response_model=list[TimelineEvent])
def timeline(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    stmt = select(TimelineEvent).where(TimelineEvent.case_id == case_id).order_by(TimelineEvent.created_at)
    return session.exec(stmt).all()
