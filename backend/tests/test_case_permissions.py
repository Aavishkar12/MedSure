import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Case, CaseMember, User
from app.routers.cases import MemberInvite, add_member


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def seed_case(session: Session, can_approve: bool) -> tuple[User, Case]:
    patient = User(id="patient", name="Lakshmi", phone="9876500001")
    viewer = User(id="viewer", name="Ravi", phone="9876500002")
    case = Case(patient_name="Lakshmi", created_by=patient.id)
    session.add(patient)
    session.add(viewer)
    session.add(case)
    session.flush()
    session.add(CaseMember(case_id=case.id, user_id=patient.id, relation="self", can_approve=True))
    session.add(CaseMember(case_id=case.id, user_id=viewer.id, relation="other", can_approve=can_approve))
    session.commit()
    return viewer, case


def test_view_only_member_cannot_create_an_approver(session: Session):
    viewer, case = seed_case(session, can_approve=False)

    with pytest.raises(HTTPException) as error:
        add_member(
            case.id,
            MemberInvite(name="New approver", phone="9876500003", can_approve=True),
            viewer,
            session,
        )

    assert error.value.status_code == 403


def test_invite_requires_a_reachable_identity(session: Session):
    approver, case = seed_case(session, can_approve=True)

    with pytest.raises(HTTPException) as error:
        add_member(case.id, MemberInvite(name="No contact"), approver, session)

    assert error.value.status_code == 422
