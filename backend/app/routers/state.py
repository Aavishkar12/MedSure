from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..deps import current_user, require_member
from ..models import CaseState, User, now
from ..notify import notify_case

router = APIRouter(tags=["state"])


class StateUpdate(BaseModel):
    """Only the fields sent are changed."""

    taken: dict[str, bool] | None = None  # dose id -> taken today
    taken_day: str | None = None  # the patient's local date for `taken`, e.g. 2026-10-01
    med_change: str | None = None  # pending | held | approved


@router.get("/cases/{case_id}/state")
def get_state(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    """Small shared state for a case: tablets taken today and the status of a medicine change."""
    require_member(session, case_id, user)
    state = session.get(CaseState, case_id)
    return state.data if state else {}


@router.patch("/cases/{case_id}/state")
def update_state(
    case_id: int, body: StateUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    require_member(session, case_id, user)
    state = session.get(CaseState, case_id) or CaseState(case_id=case_id)
    state.data = {**state.data, **body.model_dump(exclude_none=True)}
    state.updated_at = now()
    session.add(state)
    session.commit()
    session.refresh(state)
    # Silent: the other phones refresh, nothing is shown.
    notify_case(session, case_id, "", "", "state", exclude_user_id=user.id)
    return state.data
