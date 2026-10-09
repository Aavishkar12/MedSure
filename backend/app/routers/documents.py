import hashlib
import json
import logging
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

logger = logging.getLogger("medsure.documents")

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB limit
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


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
    if doc.text and doc.text.strip():
        return doc.text, []
    if not doc.path:
        raise ValueError("No file and no OCR text to read")
    text = llm.file_to_text(doc.path)
    if text:
        doc.text = text
        return text, []
    images = llm.file_to_images(doc.path)
    if not images:
        raise ValueError("Could not extract readable text or images from document")
    return "", images


def _card_data(session: Session, doc: Document) -> dict:
    if prev := _previous(session, doc, DischargeCard):
        return prev[0].data
    if not settings.groq_api_key:
        raise llm.LLMError("AI service is not configured. Please set GROQ_API_KEY on the server.")
    
    text, images = _text_and_images(doc)
    if doc.doc_type == "prescription":
        rx = llm.extract_prescription(text, images)
        # Convert prescription to card format so both card view and rx are supported
        medicines = [
            {
                "name": m.get("medicine_name", ""),
                "dose": m.get("strength", ""),
                "schedule": m.get("dosage_frequency", ""),
                "days": None,
                "purpose": m.get("instructions", ""),
                "source_page": m.get("source_page"),
            }
            for m in rx.get("medicines", [])
        ]
        return {
            "diagnosis": {"name": "Prescribed Medication", "plain": "Medications prescribed by treating doctor.", "source_page": None},
            "medicines": medicines,
            "lab_values": [],
            "precautions": [{"text": adv, "source_page": None} for adv in rx.get("general_advice", [])],
            "follow_ups": [],
            "raw_prescription": rx,
            "disclaimer": rx.get("disclaimer", "This explains your documents. It is not medical advice."),
        }
    elif doc.doc_type == "lab_report":
        lab = llm.extract_lab_report(text, images)
        lab_values = [
            {
                "name": item.get("test_name", ""),
                "value": item.get("value", ""),
                "unit": item.get("unit", ""),
                "range": item.get("reference_range", ""),
                "status": item.get("flag", "unknown") if item.get("flag") in ("low", "normal", "high") else "unknown",
                "plain": item.get("plain_explanation", ""),
                "concept": item.get("concept"),
                "source_page": item.get("source_page"),
            }
            for item in lab.get("results", [])
        ]
        return {
            "diagnosis": {"name": "Diagnostic Investigation", "plain": lab.get("summary") or "Laboratory investigation report.", "source_page": None},
            "medicines": [],
            "lab_values": lab_values,
            "precautions": [],
            "follow_ups": [],
            "raw_lab": lab,
            "disclaimer": lab.get("disclaimer", "This explains your documents. It is not medical advice."),
        }
    elif doc.doc_type == "policy":
        pol = llm.extract_policy(text, images)
        precautions = [{"text": f"Exclusion: {ex}", "source_page": None} for ex in pol.get("exclusions", [])]
        if pol.get("preauth_requirement"):
            precautions.append({"text": f"Pre-authorization: {pol['preauth_requirement']}", "source_page": None})
        return {
            "diagnosis": {
                "name": f"Insurance Policy: {pol.get('insurer') or 'Health Insurance'}",
                "plain": f"Policy #{pol.get('policy_number') or 'N/A'}. Sum insured: {pol.get('sum_insured') or 'N/A'}.",
                "source_page": pol.get("source_page"),
            },
            "medicines": [],
            "lab_values": [],
            "precautions": precautions,
            "follow_ups": [{"what": f"Claim submission deadline: {pol.get('claim_submission_deadline') or 'As per policy'}", "when": "", "source_page": None}],
            "raw_policy": pol,
            "disclaimer": pol.get("disclaimer", "This explains your documents. It is not medical advice."),
        }
    else:
        return llm.extract_discharge_card(text, images)


def _bill_items(session: Session, doc: Document) -> list[dict]:
    if prev := _previous(session, doc, BillItem):
        return [i.model_dump(exclude={"id", "case_id", "document_id"}) for i in prev]
    if not settings.groq_api_key:
        raise llm.LLMError("AI service is not configured. Please set GROQ_API_KEY on the server.")
    return llm.extract_bill(*_text_and_images(doc))


def _process_document_internal(session: Session, doc_id: int) -> None:
    doc = session.get(Document, doc_id)
    if not doc:
        return
    try:
        if doc.doc_type in ("discharge_summary", "lab_report", "prescription", "policy"):
            card_data = _card_data(session, doc)
            card = DischargeCard(case_id=doc.case_id, document_id=doc.id, data=card_data)
            session.add(card)
            session.flush()
            add_event(session, doc.case_id, "discharge_card", f"{doc.doc_type.replace('_', ' ').title()} analyzed", card.id)
        elif doc.doc_type == "bill":
            items = _bill_items(session, doc)
            for item in items:
                session.add(BillItem(case_id=doc.case_id, document_id=doc.id, **item))
            add_event(session, doc.case_id, "bill", "Bill explained", doc.id)
        elif doc.doc_type == "id_proof":
            add_event(session, doc.case_id, "document", "ID proof verified", doc.id)
        doc.status = "ready"
        doc.error = None
    except Exception as e:
        session.rollback()
        doc = session.get(Document, doc_id)
        if doc:
            doc.status = "failed"
            doc.error = str(e)
        logger.exception(f"Document processing failed for doc_id {doc_id}")
    if doc:
        session.add(doc)
        session.commit()


def process_document(doc_id: int, session: Session | None = None) -> None:
    if session is not None:
        _process_document_internal(session, doc_id)
        return
    with Session(engine) as s:
        _process_document_internal(s, doc_id)
        doc = s.get(Document, doc_id)
        if not doc:
            return
        if doc.status == "failed":
            notify_case(s, doc.case_id, "MedSure", "We couldn't process a document. Tap to check details.", "document", doc.id)
        elif doc.doc_type == "bill":
            notify_case(s, doc.case_id, "MedSure", "Your bill explanation is ready.", "bill", doc.id)
        elif doc.doc_type in ("discharge_summary", "lab_report", "prescription", "policy"):
            notify_case(s, doc.case_id, "MedSure", "Your document analysis is ready.", "discharge_card", doc.id)


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
        filename = file.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
        
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"File exceeds maximum upload size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        if len(data) == 0 and not ocr_text:
            raise HTTPException(400, "Uploaded file is empty")

        folder = Path(settings.upload_dir)
        folder.mkdir(parents=True, exist_ok=True)
        saved = folder / f"{hashlib.sha256(data).hexdigest()}{ext}"
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
    if doc.text and doc.text.strip():
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
    if not settings.groq_api_key or not settings.groq_api_key.strip():
        raise HTTPException(503, "AI service is not configured. Please set GROQ_API_KEY on the server.")
    
    question_text = (body.question or "").strip()
    if not question_text:
        raise HTTPException(422, "Question cannot be empty.")

    ready = session.exec(select(Document).where(Document.case_id == case_id, Document.status == "ready")).all()
    docs = [{"id": d.id, "doc_type": d.doc_type, "text": _qa_text(session, d)} for d in ready]
    valid_docs = [d for d in docs if d["text"]]
    if not valid_docs:
        return Answer(
            answer="No readable documents are available yet for this case. Please upload a medical document first.",
            sources=[],
            grounded=False,
        )
    try:
        return llm.answer_question(question_text, valid_docs)
    except llm.LLMError as e:
        raise HTTPException(503, str(e))
