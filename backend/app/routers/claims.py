from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import llm
from ..config import settings
from ..db import get_session
from ..deps import add_event, current_user, require_member
from ..models import BillItem, Case, CaseMember, ChecklistItem, Claim, DischargeCard, Document, Draft, User, now
from ..notify import notify_case

router = APIRouter(tags=["claims"])

DEFAULT_CHECKLIST = [
    ("Discharge summary", "discharge_summary"),
    ("Itemized final bill", "bill"),
    ("Lab / investigation reports", "lab_report"),
    ("Prescriptions", "prescription"),
    ("Patient ID proof", "id_proof"),
    ("Policy copy / e-card", "policy"),
]


class ClaimCreate(BaseModel):
    mode: str = "cashless"
    insurer: str = ""


class ClaimStatus(BaseModel):
    status: str


class ChecklistOut(BaseModel):
    label: str
    doc_type: str
    present: bool


class ClaimOut(BaseModel):
    claim: Claim
    checklist: list[ChecklistOut]
    missing_count: int


def _claim_out(session: Session, claim: Claim) -> ClaimOut:
    have = set(session.exec(select(Document.doc_type).where(Document.case_id == claim.case_id)).all())
    items = session.exec(select(ChecklistItem).where(ChecklistItem.claim_id == claim.id)).all()
    checklist = [ChecklistOut(label=i.label, doc_type=i.doc_type, present=i.doc_type in have) for i in items]
    return ClaimOut(claim=claim, checklist=checklist, missing_count=sum(not c.present for c in checklist))


def _get_claim(session: Session, claim_id: int, user: User) -> Claim:
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    require_member(session, claim.case_id, user)
    return claim


def _get_draft(session: Session, draft_id: int, user: User) -> Draft:
    draft = session.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    require_member(session, draft.case_id, user)
    return draft


@router.post("/cases/{case_id}/claims", response_model=ClaimOut, status_code=201)
def create_claim(
    case_id: int, body: ClaimCreate, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    require_member(session, case_id, user)
    claim = Claim(case_id=case_id, mode=body.mode, insurer=body.insurer)
    session.add(claim)
    session.flush()
    for label, doc_type in DEFAULT_CHECKLIST:
        session.add(ChecklistItem(claim_id=claim.id, label=label, doc_type=doc_type))
    add_event(session, case_id, "claim", f"{body.mode.capitalize()} claim started", claim.id)
    session.commit()
    session.refresh(claim)
    return _claim_out(session, claim)


@router.get("/cases/{case_id}/claims", response_model=list[ClaimOut])
def list_claims(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    claims = session.exec(select(Claim).where(Claim.case_id == case_id)).all()
    return [_claim_out(session, c) for c in claims]


@router.patch("/claims/{claim_id}", response_model=ClaimOut)
def update_claim_status(
    claim_id: int, body: ClaimStatus, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    claim = _get_claim(session, claim_id, user)
    claim.status = body.status
    session.add(claim)
    add_event(session, claim.case_id, "claim", f"Claim status: {body.status.replace('_', ' ')}", claim.id)
    session.commit()
    session.refresh(claim)
    notify_case(
        session, claim.case_id, "MedSure", "Your insurance claim status changed.", "claim", claim.id,
        exclude_user_id=user.id,
    )
    return _claim_out(session, claim)


class DraftCreate(BaseModel):
    kind: Literal["claim_letter", "appeal_letter"] = "claim_letter"
    notes: str = ""  # from the family, e.g. the reason the insurer gave for a denial


def _letter_facts(session: Session, claim: Claim, notes: str) -> dict:
    case = session.get(Case, claim.case_id)
    card = session.exec(
        select(DischargeCard).where(DischargeCard.case_id == claim.case_id).order_by(DischargeCard.id.desc())
    ).first()
    bill_total = sum(session.exec(select(BillItem.amount).where(BillItem.case_id == claim.case_id)).all())
    checklist = _claim_out(session, claim).checklist
    return {
        "patient_name": case.patient_name,
        "insurer": claim.insurer or None,
        "claim_type": claim.mode,
        "claim_status": claim.status,
        "diagnosis": card.data.get("diagnosis", {}).get("name") if card else None,
        "bill_total": f"Rs {bill_total:,.2f}" if bill_total else None,
        "documents_enclosed": [c.label for c in checklist if c.present],
        "documents_missing": [c.label for c in checklist if not c.present],
        "notes_from_family": notes or None,
    }


class DraftEdit(BaseModel):
    body: str


@router.post("/claims/{claim_id}/drafts", response_model=Draft, status_code=201)
def create_draft(
    claim_id: int, body: DraftCreate, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    claim = _get_claim(session, claim_id, user)
    if settings.groq_api_key:
        try:
            text = llm.draft_letter(body.kind, _letter_facts(session, claim, body.notes))
        except llm.LLMError as e:
            raise HTTPException(503, str(e))
    else:  # canned placeholder when no key is set
        text = f"To the Claims Manager, {claim.insurer or '[Insurer]'}\n\n[AI-drafted {body.kind.replace('_', ' ')} goes here]"
    draft = Draft(case_id=claim.case_id, claim_id=claim.id, kind=body.kind, body=text)
    session.add(draft)
    session.flush()
    add_event(session, claim.case_id, "draft", f"Draft {body.kind.replace('_', ' ')} ready for review", draft.id)
    session.commit()
    session.refresh(draft)
    notify_case(
        session, claim.case_id, "MedSure", "A draft letter is waiting for review.", "draft", draft.id,
        exclude_user_id=user.id,
    )
    return draft


@router.get("/drafts/{draft_id}", response_model=Draft)
def get_draft(draft_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _get_draft(session, draft_id, user)


@router.patch("/drafts/{draft_id}", response_model=Draft)
def edit_draft(
    draft_id: int, body: DraftEdit, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    draft = _get_draft(session, draft_id, user)
    if draft.status == "sent":
        raise HTTPException(409, "Draft already sent")
    # Any edit resets approval: what gets sent is exactly what was approved.
    draft.body, draft.status, draft.approved_by, draft.approved_at = body.body, "draft", None, None
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/approve", response_model=Draft)
def approve_draft(draft_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    draft = _get_draft(session, draft_id, user)
    if draft.status != "draft":
        raise HTTPException(409, f"Draft is already {draft.status}")
    if not session.get(CaseMember, (draft.case_id, user.id)).can_approve:
        raise HTTPException(403, "You can view this case but not approve for it")
    draft.status, draft.approved_by, draft.approved_at = "approved", user.id, now()
    session.add(draft)
    add_event(session, draft.case_id, "draft", f"{draft.kind.replace('_', ' ').capitalize()} approved", draft.id)
    session.commit()
    session.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/send", response_model=Draft)
def send_draft(draft_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    draft = _get_draft(session, draft_id, user)
    if draft.status != "approved":
        raise HTTPException(409, "A family member must approve this draft before it can be sent")
    # Nothing is transmitted by the backend in the MVP; the app shares the approved text.
    draft.status = "sent"
    session.add(draft)
    add_event(session, draft.case_id, "draft", f"{draft.kind.replace('_', ' ').capitalize()} sent", draft.id)
    session.commit()
    session.refresh(draft)
    return draft
