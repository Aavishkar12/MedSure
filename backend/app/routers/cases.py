from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..deps import current_user, require_member
from ..models import Case, CaseMember, TimelineEvent, User

router = APIRouter(tags=["cases"])


class CaseCreate(BaseModel):
    patient_name: str
    role: str = "family"


class MemberAdd(BaseModel):
    user_id: str
    role: str = "family"


@router.post("/cases", response_model=Case, status_code=201)
def create_case(body: CaseCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    case = Case(patient_name=body.patient_name, created_by=user.id)
    session.add(case)
    session.flush()
    session.add(CaseMember(case_id=case.id, user_id=user.id, role=body.role))
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


@router.post("/cases/{case_id}/members", response_model=CaseMember, status_code=201)
def add_member(
    case_id: int, body: MemberAdd, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    require_member(session, case_id, user)
    if not session.get(User, body.user_id):
        session.add(User(id=body.user_id))
    member = session.merge(CaseMember(case_id=case_id, user_id=body.user_id, role=body.role))
    session.commit()
    return member


@router.get("/cases/{case_id}/timeline", response_model=list[TimelineEvent])
def timeline(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    stmt = select(TimelineEvent).where(TimelineEvent.case_id == case_id).order_by(TimelineEvent.created_at)
    return session.exec(stmt).all()
