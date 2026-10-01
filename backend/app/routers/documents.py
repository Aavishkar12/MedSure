import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import llm
from ..config import settings
from ..db import engine, get_session
from ..deps import add_event, current_user, require_member
from ..models import DOC_TYPES, BillItem, DischargeCard, Document, User
from ..notify import notify_case

router = APIRouter(tags=["documents"])

# Canned results returned when GROQ_API_KEY is unset, so Android can build against the real shapes.
STUB_CARD = {
    "diagnosis": {"name": "Acute kidney injury", "plain": "Your kidneys were temporarily not filtering well.", "source_page": 1},
    "medicines": [
        {"name": "Pantoprazole", "dose": "40 mg", "schedule": "once daily before breakfast", "days": 14,
         "purpose": "Protects the stomach lining.", "source_page": 2}
    ],
    "lab_values": [
        {"name": "Creatinine", "value": "2.1", "unit": "mg/dL", "range": "0.7-1.3", "status": "high",
         "plain": "A kidney marker that is above normal.", "concept": "kidney_function", "source_page": 1}
    ],
    "precautions": [{"text": "Avoid painkillers like ibuprofen unless your doctor says so.", "source_page": 2}],
    "follow_ups": [{"what": "Nephrology review with repeat creatinine", "when": "in 7 days", "source_page": 2}],
    "disclaimer": "This explains your documents. It is not medical advice.",
}
STUB_BILL = [
    {"description": "Renal function test x3", "amount": 2400.0, "explanation": "Blood tests that check kidney function.",
     "worth_asking": True, "ask_reason": "Billed three times; confirm three tests were done.", "concept": "kidney_function"},
    {"description": "Room charges (3 days)", "amount": 13500.0, "explanation": "Daily charge for the hospital room.",
     "worth_asking": False, "ask_reason": None, "concept": None},
]


def _previous(session: Session, doc: Document, model):
    """Results already extracted from an identical file, so repeats never hit the LLM."""
    stmt = (
        select(model)
        .join(Document, Document.id == model.document_id)
        .where(Document.sha256 == doc.sha256, Document.doc_type == doc.doc_type, Document.id != doc.id)
    )
    return session.exec(stmt).all()


def _text_and_images(doc: Document) -> tuple[str, list[bytes]]:
    """OCR text from the app wins, then a PDF's own text layer, then page images for the vision model."""
    if doc.text:
        return doc.text, []
    if not doc.path:
        raise ValueError("No file and no OCR text to read")
    text = llm.file_to_text(doc.path)
    if text:
        doc.text = text
        return text, []
    return "", llm.file_to_images(doc.path)


def _card_data(session: Session, doc: Document) -> dict:
    if prev := _previous(session, doc, DischargeCard):
        return prev[0].data
    if not settings.groq_api_key:
        return STUB_CARD
    return llm.extract_discharge_card(*_text_and_images(doc))


def _bill_items(session: Session, doc: Document) -> list[dict]:
    if prev := _previous(session, doc, BillItem):
        return [i.model_dump(exclude={"id", "case_id", "document_id"}) for i in prev]
    if not settings.groq_api_key:
        return STUB_BILL
    return llm.extract_bill(*_text_and_images(doc))


def process_document(doc_id: int) -> None:
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        try:
            if doc.doc_type in ("discharge_summary", "lab_report", "prescription"):
                card = DischargeCard(case_id=doc.case_id, document_id=doc.id, data=_card_data(session, doc))
                session.add(card)
                session.flush()
                add_event(session, doc.case_id, "discharge_card", "Discharge Card ready", card.id)
            elif doc.doc_type == "bill":
                for item in _bill_items(session, doc):
                    session.add(BillItem(case_id=doc.case_id, document_id=doc.id, **item))
                add_event(session, doc.case_id, "bill", "Bill explained", doc.id)
            doc.status = "ready"
        except Exception as e:  # surfaced to the app via status/error
            session.rollback()
            doc = session.get(Document, doc_id)
            doc.status, doc.error = "failed", str(e)
        session.add(doc)
        session.commit()
        if doc.status == "failed":
            notify_case(session, doc.case_id, "MedSure", "We couldn't read a document. Tap to try again.", "document", doc.id)
        elif doc.doc_type == "bill":
            notify_case(session, doc.case_id, "MedSure", "Your bill explanation is ready.", "bill", doc.id)
        elif doc.doc_type in ("discharge_summary", "lab_report", "prescription"):
            notify_case(session, doc.case_id, "MedSure", "Your Discharge Card is ready.", "discharge_card", doc.id)


@router.post("/cases/{case_id}/documents", response_model=Document, status_code=202)
async def upload_document(
    case_id: int,
    background: BackgroundTasks,
    doc_type: str = Form(...),
    file: UploadFile | None = File(None),
    ocr_text: str | None = Form(None, description="On-device OCR text. Mark pages as [Page 1], [Page 2]..."),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {DOC_TYPES}")
    ocr_text = (ocr_text or "").strip() or None
    if not file and not ocr_text:
        raise HTTPException(422, "Send a file, ocr_text, or both")

    path, filename = "", "ocr-text"
    data = (ocr_text or "").encode()
    if file:
        data = await file.read()
        filename = file.filename or "upload"
        folder = Path(settings.upload_dir)
        folder.mkdir(parents=True, exist_ok=True)
        saved = folder / f"{hashlib.sha256(data).hexdigest()}{Path(filename).suffix.lower()}"
        saved.write_bytes(data)
        path = str(saved)
    digest = hashlib.sha256(data).hexdigest()

    doc = Document(case_id=case_id, doc_type=doc_type, filename=filename, path=path, sha256=digest, text=ocr_text)
    session.add(doc)
    session.flush()
    add_event(session, case_id, "document", f"Uploaded {doc_type.replace('_', ' ')}", doc.id)
    session.commit()
    session.refresh(doc)
    background.add_task(process_document, doc.id)
    return doc


@router.get("/cases/{case_id}/documents", response_model=list[Document])
def list_documents(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    return session.exec(select(Document).where(Document.case_id == case_id)).all()


@router.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    require_member(session, doc.case_id, user)
    return doc


@router.get("/cases/{case_id}/discharge-card", response_model=DischargeCard)
def discharge_card(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    stmt = select(DischargeCard).where(DischargeCard.case_id == case_id).order_by(DischargeCard.id.desc())
    card = session.exec(stmt).first()
    if not card:
        raise HTTPException(404, "No Discharge Card yet")
    return card


class BillOut(BaseModel):
    total: float
    items: list[BillItem]


@router.get("/cases/{case_id}/bill", response_model=BillOut)
def bill(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    items = session.exec(select(BillItem).where(BillItem.case_id == case_id)).all()
    return BillOut(total=sum(i.amount for i in items), items=items)


def _qa_text(session: Session, doc: Document) -> str:
    """The document's own text, or its extracted data when it was read from images."""
    if doc.text:
        return doc.text
    cards = session.exec(select(DischargeCard).where(DischargeCard.document_id == doc.id)).all()
    items = session.exec(select(BillItem).where(BillItem.document_id == doc.id)).all()
    data = [c.data for c in cards] + [i.model_dump(include={"description", "amount", "explanation"}) for i in items]
    return json.dumps(data) if data else ""


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    answer: str
    sources: list[dict]
    grounded: bool


@router.post("/cases/{case_id}/ask", response_model=Answer)
def ask(case_id: int, body: Question, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    if not settings.groq_api_key:
        return Answer(answer=llm.qa.NOT_FOUND, sources=[], grounded=False)
    ready = session.exec(select(Document).where(Document.case_id == case_id, Document.status == "ready")).all()
    docs = [{"id": d.id, "doc_type": d.doc_type, "text": _qa_text(session, d)} for d in ready]
    try:
        return llm.answer_question(body.question, [d for d in docs if d["text"]])
    except llm.LLMError as e:
        raise HTTPException(503, str(e))
