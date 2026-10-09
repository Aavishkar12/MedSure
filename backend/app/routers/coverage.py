"""Insurance coverage check: the case's bill lines compared with its insurance policy."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import llm
from ..config import settings
from ..db import get_session
from ..deps import add_event, current_user, require_member
from ..models import BillItem, CoverageReport, DischargeCard, Document, PolicySummary, User
from ..notify import notify_case

logger = logging.getLogger("medsure.coverage")

router = APIRouter(tags=["coverage"])


def refresh_coverage(session: Session, case_id: int) -> Optional[CoverageReport]:
    """
    Compares every bill line on the case with the newest policy and stores the result.
    Returns None while the case has no bill lines or no policy yet.
    """
    policy = session.exec(
        select(PolicySummary).where(PolicySummary.case_id == case_id).order_by(PolicySummary.id.desc())
    ).first()
    items = session.exec(select(BillItem).where(BillItem.case_id == case_id).order_by(BillItem.id)).all()
    if not policy or not items:
        return None

    policy_doc = session.get(Document, policy.document_id)
    policy_text = (policy_doc.text or "") if policy_doc else ""
    card = session.exec(
        select(DischargeCard).where(DischargeCard.case_id == case_id).order_by(DischargeCard.id.desc())
    ).first()
    diagnosis = (card.data.get("diagnosis") or {}).get("name", "") if card else ""
    lines = [{"id": i.id, "description": i.description, "amount": i.amount} for i in items]

    if settings.groq_api_key.strip():
        try:
            data = llm.compare_bill_to_policy(lines, policy.data, policy_text, diagnosis)
        except llm.LLMError as e:
            logger.warning(f"Coverage AI unavailable for case {case_id}: {e}")
            data = llm.rule_based_report(lines, policy.data, policy_text)
            data["notes"].insert(0, f"AI review failed ({e}); showing a basic check. Try again later.")
    else:
        data = llm.rule_based_report(lines, policy.data, policy_text)
    data["policy_document_id"] = policy.document_id

    report = CoverageReport(case_id=case_id, data=data)
    session.add(report)
    session.flush()
    add_event(session, case_id, "coverage", "Insurance coverage checked", report.id)
    session.commit()
    session.refresh(report)
    notify_case(session, case_id, "MedSure", "We compared your bill with your insurance policy.", "coverage", report.id)
    return report


@router.get("/cases/{case_id}/coverage", response_model=CoverageReport)
def get_coverage(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The latest comparison of the bill with the insurance policy."""
    require_member(session, case_id, user)
    stmt = select(CoverageReport).where(CoverageReport.case_id == case_id).order_by(CoverageReport.id.desc())
    report = session.exec(stmt).first()
    if not report:
        raise HTTPException(404, "No coverage check yet. Upload both the bill and the insurance policy.")
    return report


@router.post("/cases/{case_id}/coverage", response_model=CoverageReport, status_code=201)
def run_coverage(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Runs the comparison again now, e.g. after a document was added or the AI was busy."""
    require_member(session, case_id, user)
    report = refresh_coverage(session, case_id)
    if report is None:
        raise HTTPException(409, "Upload both the hospital bill and the insurance policy first.")
    return report
