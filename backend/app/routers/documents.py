"""Document upload and reading.

Every document goes through the same steps:
  file -> text (PDF text layer, OCR from the phone, or Tesseract) -> what kind of document it is
       -> structured data (the LLM when GROQ_API_KEY is set; the rule-based parsers otherwise)
Nothing here returns sample data: what the app shows comes from the document that was uploaded.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import llm
from ..config import settings
from ..db import engine, get_session
from ..deps import add_event, current_user, require_member
from ..models import (
    DOC_TYPE_ALIASES,
    DOC_TYPES,
    BillItem,
    DischargeCard,
    Document,
    PolicySummary,
    ProcessingJob,
    User,
)
from ..notify import notify_case
from ..pipeline.runner import run_pipeline_for_document
from ..pipeline.schemas import CaseExtractionEnvelope, DocumentExtractionEnvelope
from .coverage import refresh_coverage

logger = logging.getLogger("medsure.documents")

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
CARD_TYPES = ("discharge_summary", "lab_report", "prescription")
# Above this confidence the text decides the document type, even over the category it was uploaded in.
CLASSIFIER_OVERRIDE_CONFIDENCE = 0.8
NO_AI = "AI reading is not configured on the server (GROQ_API_KEY), and the document could not be read without it."


# ---------- Reading one document ----------

def _doc_type(hint: str, envelope) -> str:
    """The upload category, corrected by the classifier when the text clearly says otherwise."""
    classified = DOC_TYPE_ALIASES.get(envelope.doc_type, envelope.doc_type)
    confident = (envelope.classification_confidence or 0) >= CLASSIFIER_OVERRIDE_CONFIDENCE
    if classified in DOC_TYPES and (hint not in DOC_TYPES or (confident and hint != "prescription")):
        return classified
    return hint if hint in DOC_TYPES else "discharge_summary"


def _previous(session: Session, doc: Document, model):
    """Results already extracted from an identical file, so repeats never hit the LLM."""
    stmt = (
        select(model)
        .join(Document, Document.id == model.document_id)
        .where(Document.sha256 == doc.sha256, Document.doc_type == doc.doc_type, Document.id != doc.id)
    )
    return session.exec(stmt).all()


def _cached_extraction(session: Session, doc: Document) -> Optional[dict]:
    """Return an identical document's durable parse, excluding demo data."""
    cached = session.exec(
        select(Document)
        .where(
            Document.sha256 == doc.sha256,
            Document.id != doc.id,
            Document.extraction.is_not(None),
            Document.extraction_method != "demo_fallback",
        )
        .order_by(Document.id.desc())
    ).first()
    if not cached or not cached.extraction:
        return None
    return {**cached.extraction, "raw_text": cached.text or ""}


def _case_extraction(session: Session, case_id: int) -> CaseExtractionEnvelope:
    """Build the case extraction response from PostgreSQL, never local disk."""
    documents = []
    rows = session.exec(
        select(Document)
        .where(Document.case_id == case_id, Document.extraction.is_not(None))
        .order_by(Document.id)
    ).all()
    for row in rows:
        try:
            documents.append(DocumentExtractionEnvelope.model_validate(row.extraction))
        except Exception:
            logger.exception("Ignoring invalid extraction JSON for document %s", row.id)
    return CaseExtractionEnvelope(
        case_id=str(case_id), total_documents=len(documents), documents=documents
    )


def _llm_inputs(doc: Document, text: str, method: str) -> tuple[str, list[bytes]]:
    """
    Clean text alone when the document has a text layer. For scans and photos, the page images with
    whatever OCR text there is (from the phone or Tesseract) as a hint.
    The vision model only sees the first few pages, so a longer scan that already has OCR text for
    every page is read from that text instead: no page is silently dropped.
    """
    if text and method == "text_layer":
        return text, []
    images = llm.file_to_images(doc.path) if doc.path and Path(doc.path).suffix.lower() != ".txt" else []
    if text and method == "device_ocr" and text.count("[Page ") > len(images):
        return text, []
    if images:
        return text, images
    if text:
        return text, []
    raise ValueError("Could not find any readable text or pages in this document")


def _card_from_llm(doc_type: str, text: str, images: list[bytes]) -> dict:
    if doc_type == "prescription":
        rx = llm.extract_prescription(text, images)
        return {
            "kind": "prescription",
            "summary": "",
            "diagnosis": {"name": "Prescription", "plain": "Medicines prescribed by the treating doctor.", "source_page": None},
            "medicines": [
                {
                    "name": m.get("medicine_name", ""),
                    "dose": m.get("strength") or "",
                    "schedule": m.get("dosage_frequency") or "",
                    "days": None,
                    "purpose": m.get("instructions") or "",
                    "source_page": m.get("source_page"),
                }
                for m in rx.get("medicines", [])
            ],
            "lab_values": [],
            "precautions": [{"text": adv, "source_page": None} for adv in rx.get("general_advice", [])],
            "warning_signs": [],
            "follow_ups": [],
            "raw_prescription": rx,
            "disclaimer": rx["disclaimer"],
        }
    if doc_type == "lab_report":
        lab = llm.extract_lab_report(text, images)
        return {
            "kind": "lab_report",
            "summary": lab.get("summary") or "",
            "diagnosis": {"name": "Test report", "plain": lab.get("summary") or "Results of your tests.", "source_page": None},
            "medicines": [],
            "lab_values": [
                {
                    "name": r.get("test_name", ""),
                    "value": r.get("value", ""),
                    "unit": r.get("unit", ""),
                    "range": r.get("reference_range", ""),
                    "status": r["flag"] if r.get("flag") in ("low", "normal", "high") else "unknown",
                    "plain": r.get("plain_explanation", ""),
                    "concept": r.get("concept"),
                    "source_page": r.get("source_page"),
                }
                for r in lab.get("results", [])
            ],
            "precautions": [],
            "warning_signs": [],
            "follow_ups": [],
            "raw_lab": lab,
            "disclaimer": lab["disclaimer"],
        }
    return {"kind": "discharge_summary", **llm.extract_discharge_card(text, images)}


def _card_from_rules(fields: dict, envelope_type: str) -> dict:
    """The rule-based parse of a discharge summary or lab report, in Discharge Card form."""
    card = {
        "kind": "discharge_summary", "summary": "", "medicines": [], "lab_values": [], "precautions": [],
        "warning_signs": [], "follow_ups": [], "source": "rules", "disclaimer": llm.extract.DISCLAIMER,
    }
    if envelope_type == "discharge_summary" and fields.get("diagnosis"):
        follow = fields.get("follow_up") or {}
        card.update(
            hospital=fields.get("hospital"),
            doctor=fields.get("consultant"),
            admission_date=fields.get("admission_date"),
            discharge_date=fields.get("discharge_date"),
            diagnosis={"name": fields["diagnosis"], "plain": "", "source_page": None},
            medicines=[
                {"name": m.get("name") or "", "dose": m.get("dose") or "", "schedule": m.get("frequency") or "",
                 "days": None, "purpose": m.get("purpose") or "", "source_page": None}
                for m in fields.get("medicines", []) if m.get("name")
            ],
            precautions=[{"text": a, "source_page": None} for a in fields.get("advice", [])],
            warning_signs=[{"text": w, "source_page": None} for w in fields.get("warning_signs", [])],
            follow_ups=[
                {"what": follow.get("note") or follow.get("department") or "Follow-up visit",
                 "when": " ".join(x for x in (follow.get("date"), follow.get("time")) if x), "source_page": None}
            ] if follow.get("date") or follow.get("note") else [],
        )
        return card
    if envelope_type == "investigation_report" and fields.get("tests"):
        status = {"low": "low", "high": "high", "normal": "normal"}
        card.update(
            kind="lab_report",
            summary=fields.get("impression") or "",
            diagnosis={"name": "Test report", "plain": fields.get("impression") or "", "source_page": None},
            lab_values=[
                {"name": t.get("name") or "", "value": t.get("value") or "", "unit": t.get("unit") or "",
                 "range": t.get("reference_range") or "", "status": status.get((t.get("flag") or "").lower(), "unknown"),
                 "plain": "", "concept": None, "source_page": None}
                for t in fields["tests"]
            ],
        )
        return card
    raise ValueError(NO_AI)


def _policy_from_rules(fields: dict) -> dict:
    if not (fields.get("insurer") or fields.get("sum_insured") or fields.get("policy_no")):
        raise ValueError(NO_AI)
    period = fields.get("policy_period") or {}
    days = fields.get("pre_post_hospitalisation_days") or {}
    return {
        "policy_number": fields.get("policy_no"),
        "insurer": fields.get("insurer"),
        "policyholder_name": fields.get("policyholder"),
        "insured_members": [m.get("name") for m in fields.get("insured_members", []) if m.get("name")],
        "policy_start": period.get("start"),
        "policy_end": period.get("end"),
        "sum_insured": fields.get("sum_insured"),
        "room_rent_limit_per_day": fields.get("room_rent_limit_per_day"),
        "copay_percent": fields.get("copay_percent"),
        "pre_hospitalisation_days": days.get("pre"),
        "post_hospitalisation_days": days.get("post"),
        "non_payable_items": fields.get("non_payable_categories", []),
        "exclusions": [],
        "claim_submission_deadline": (
            f"Within {fields['claim_submission_days']} days of discharge" if fields.get("claim_submission_days") else None
        ),
        "source": "rules",
        "disclaimer": llm.extract.DISCLAIMER,
    }


BILL_COLUMNS = ("description", "amount", "explanation", "worth_asking", "ask_reason", "concept")


def _with_quantity(description: str, quantity, unit_price) -> str:
    """"Room rent" -> "Room rent (5 x Rs 6000)" when the bill shows several units at a rate."""
    try:
        qty, rate = float(quantity), float(unit_price)
    except (TypeError, ValueError):
        return description
    if qty <= 1 or rate <= 0 or " x Rs " in description:
        return description
    return f"{description} ({qty:g} x Rs {rate:g})"


def _read(session: Session, doc: Document, text: str, method: str, envelope) -> None:
    """Turns the document's text into its structured rows: Discharge Card, bill lines or policy terms."""
    ai = bool(settings.groq_api_key.strip())
    # Demo sample data (DEMO_FALLBACK) is for inspecting the pipeline only; it never becomes a patient's card.
    fields = envelope.fields if envelope.extraction_method != "demo_fallback" else {}
    if doc.doc_type in CARD_TYPES:
        if prev := _previous(session, doc, DischargeCard):
            data = prev[0].data
        elif ai:
            data = _card_from_llm(doc.doc_type, *_llm_inputs(doc, text, method))
        else:
            data = _card_from_rules(fields, envelope.doc_type)
        card = DischargeCard(case_id=doc.case_id, document_id=doc.id, data=data)
        session.add(card)
        session.flush()
        title = "Discharge Card ready" if data.get("kind", "discharge_summary") == "discharge_summary" else (
            f"{doc.doc_type.replace('_', ' ').capitalize()} explained")
        add_event(session, doc.case_id, "discharge_card", title, card.id)
    elif doc.doc_type == "bill":
        if prev := _previous(session, doc, BillItem):
            items = [i.model_dump(include=set(BILL_COLUMNS)) for i in prev]
        elif ai:
            items = llm.extract_bill(*_llm_inputs(doc, text, method))
            for item in items:
                item["description"] = _with_quantity(item["description"], item.get("quantity"), item.get("unit_price"))
        else:
            items = [
                {"description": _with_quantity(li["description"], li.get("qty"), li.get("rate")), "amount": li["amount"]}
                for li in fields.get("line_items", []) if li.get("description") and li.get("amount") is not None
            ]
            if not items:
                raise ValueError(NO_AI)
        if not items:
            raise ValueError("No billed items were found in this document")
        for item in items:
            session.add(BillItem(case_id=doc.case_id, document_id=doc.id, **{k: item[k] for k in BILL_COLUMNS if k in item}))
        add_event(session, doc.case_id, "bill", "Bill explained", doc.id)
    elif doc.doc_type == "policy":
        if prev := _previous(session, doc, PolicySummary):
            data = prev[0].data
        elif ai:
            data = llm.extract_policy(*_llm_inputs(doc, text, method))
        else:
            data = _policy_from_rules(fields)
        session.add(PolicySummary(case_id=doc.case_id, document_id=doc.id, data=data))
        add_event(session, doc.case_id, "policy", "Insurance policy read", doc.id)
    # id_proof: stored for the claim checklist; there is nothing to extract.


def _process(session: Session, doc_id: int) -> Optional[dict]:
    """Reads one document and saves the result. Returns the pipeline's summary for job tracking."""
    doc = session.get(Document, doc_id)
    if not doc:
        return None
    info: dict = {"doc_id": doc.id, "filename": doc.filename}
    extraction: Optional[dict] = None
    extracted_text: Optional[str] = None
    try:
        envelope, text = run_pipeline_for_document(
            case_id=doc.case_id,
            doc_id=doc.id,
            file_path=doc.path,
            file_hash=doc.sha256,
            source_filename=doc.filename,
            hint_doc_type=doc.doc_type,
            supplied_text=doc.text,
            cached=_cached_extraction(session, doc),
        )
        extraction = envelope.model_dump(mode="json")
        extracted_text = text
        doc.classified_type = envelope.doc_type
        doc.extraction_method = envelope.extraction_method
        doc.extraction = extraction
        doc.doc_type = _doc_type(doc.doc_type, envelope)
        if text.strip():
            doc.text = text
        info.update(doc_type=doc.doc_type, pages=envelope.pages, extraction_method=envelope.extraction_method,
                    warnings=envelope.warnings)
        _read(session, doc, text, envelope.extraction_method, envelope)
        doc.status, doc.error = "ready", None
    except Exception as e:  # surfaced to the app via status/error
        logger.exception(f"Document processing failed for doc_id {doc_id}")
        session.rollback()
        doc = session.get(Document, doc_id)
        # Parsing may have succeeded before the user-facing LLM/card step failed.
        # Keep that deterministic result available for diagnostics and retry.
        if extraction is not None:
            doc.extraction = extraction
            doc.classified_type = extraction.get("doc_type")
            doc.extraction_method = extraction.get("extraction_method")
            if extracted_text and extracted_text.strip():
                doc.text = extracted_text
        doc.status = "failed"
        doc.error = str(e) if isinstance(e, (ValueError, llm.LLMError)) else "We couldn't read this document."
    session.add(doc)
    session.commit()
    info.update(status=doc.status, error=doc.error)

    if doc.status == "ready" and doc.doc_type in ("bill", "policy"):
        try:
            refresh_coverage(session, doc.case_id)
        except Exception:
            logger.exception(f"Coverage check failed for case {doc.case_id}")
    return info


def _notify(session: Session, doc: Document) -> None:
    if doc.status == "failed":
        notify_case(session, doc.case_id, "MedSure", "We couldn't read a document. Tap to check details.", "document", doc.id)
    elif doc.doc_type == "bill":
        notify_case(session, doc.case_id, "MedSure", "Your bill explanation is ready.", "bill", doc.id)
    elif doc.doc_type == "policy":
        notify_case(session, doc.case_id, "MedSure", "Your insurance policy has been read.", "policy", doc.id)
    elif doc.doc_type in CARD_TYPES:
        notify_case(session, doc.case_id, "MedSure", "Your Discharge Card is ready.", "discharge_card", doc.id)


def process_document(doc_id: int, session: Session | None = None) -> Optional[dict]:
    if session is not None:
        return _process(session, doc_id)
    with Session(engine) as s:
        info = _process(s, doc_id)
        if doc := s.get(Document, doc_id):
            _notify(s, doc)
        return info


def execute_job_processing(job_id: str, case_id: int, doc_ids: List[int]) -> None:
    """Background worker: reads each document of an upload and records progress the app can poll."""
    with Session(engine) as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            return
        files, warnings = [], list(job.warnings or [])
        for idx, doc_id in enumerate(doc_ids, start=1):
            job.stage = "extracting"
            job.progress = round(0.1 + (idx - 0.5) / len(doc_ids) * 0.85, 2)
            session.add(job)
            session.commit()

            info = process_document(doc_id) or {"doc_id": doc_id, "status": "failed", "error": "Document not found"}
            files.append(info)
            warnings.extend(f"[{info.get('filename', doc_id)}] {w}" for w in info.get("warnings", []))
            if info.get("status") == "failed":
                warnings.append(f"Failed processing {info.get('filename', doc_id)}: {info.get('error')}")

            session.refresh(job)
            job.processed_files = idx
            job.files = files + job.files[idx:]  # finished files, then the ones still waiting
            job.warnings = warnings
            job.progress = round(0.1 + idx / len(doc_ids) * 0.85, 2)
            session.add(job)
            session.commit()

        job.stage = "failed" if files and all(f.get("status") == "failed" for f in files) else "completed"
        if job.stage == "failed":
            job.error = "; ".join(str(f.get("error")) for f in files)[:500]
        job.progress = 1.0
        job.completed_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()


# ---------- Upload ----------

class UploadResultOut(BaseModel):
    job_id: str
    case_id: int
    documents: List[Document]


class JobStatusOut(BaseModel):
    job_id: str
    case_id: int
    stage: str
    progress: float
    total_files: int
    processed_files: int
    files: List[Dict[str, Any]]
    warnings: List[str]
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


def _save_upload(data: bytes, ext: str) -> str:
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder / f"{hashlib.sha256(data).hexdigest()}{ext}"
    saved.write_bytes(data)
    return str(saved)


@router.post("/cases/{case_id}/documents", response_model=UploadResultOut, status_code=202)
async def upload_documents(
    case_id: int,
    background: BackgroundTasks,
    files: List[UploadFile] = File(default=[]),
    file: Optional[UploadFile] = File(None),
    doc_type: Optional[str] = Form(None, description=f"One of {DOC_TYPES}; detected from the text when left out"),
    ocr_text: Optional[str] = Form(None, description="On-device OCR text. Mark pages as [Page 1], [Page 2]..."),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    doc_type = DOC_TYPE_ALIASES.get(doc_type or "", doc_type or "")
    if doc_type and doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {DOC_TYPES}")
    uploads = [f for f in ([file] if file else []) + list(files or []) if f is not None and f.filename]
    ocr_text = (ocr_text or "").strip() or None
    if not uploads and not ocr_text:
        raise HTTPException(422, "Send a file, ocr_text, or both")

    # Read and check everything before saving anything, so a bad file rejects the whole upload.
    payloads = []
    limit_mb = settings.upload_max_size_bytes / (1024 * 1024)
    for up in uploads:
        ext = Path(up.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
        data = await up.read()
        if len(data) > settings.upload_max_size_bytes:
            raise HTTPException(413, f"File '{up.filename}' exceeds the maximum upload size of {limit_mb:.0f} MB")
        if not data and not ocr_text:
            raise HTTPException(400, f"Uploaded file '{up.filename}' is empty")
        payloads.append((up.filename, ext, data))

    created: List[Document] = []
    for filename, ext, data in payloads:
        doc = Document(
            case_id=case_id, doc_type=doc_type or "unknown", filename=filename,
            path=_save_upload(data, ext) if data else "", sha256=hashlib.sha256(data or ocr_text.encode()).hexdigest(),
            # Phone OCR text belongs to the file it was read from; it only makes sense with a single file.
            text=ocr_text if len(payloads) == 1 else None,
        )
        session.add(doc)
        created.append(doc)
    if not payloads:  # OCR text on its own
        data = ocr_text.encode()
        created.append(Document(
            case_id=case_id, doc_type=doc_type or "unknown", filename="ocr-text.txt",
            path=_save_upload(data, ".txt"), sha256=hashlib.sha256(data).hexdigest(), text=ocr_text,
        ))
        session.add(created[-1])
    session.flush()
    for doc in created:
        add_event(session, case_id, "document", f"Uploaded {doc.filename}", doc.id)

    job = ProcessingJob(
        id=uuid.uuid4().hex, case_id=case_id, stage="uploading", progress=0.1, total_files=len(created),
        files=[{"doc_id": d.id, "filename": d.filename, "status": "processing"} for d in created],
    )
    session.add(job)
    session.commit()
    for d in created:
        session.refresh(d)
    background.add_task(execute_job_processing, job.id, case_id, [d.id for d in created])
    return UploadResultOut(job_id=job.id, case_id=case_id, documents=created)


@router.post("/documents/{doc_id}/retry", response_model=Document, status_code=202)
def retry_document(
    doc_id: int, background: BackgroundTasks, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    """Reads a document that failed again, e.g. after the AI key was set or the service was busy."""
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    require_member(session, doc.case_id, user)
    if doc.status != "failed":
        raise HTTPException(409, f"Document is {doc.status}, not failed")
    doc.status, doc.error = "processing", None
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(process_document, doc.id)
    return doc


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job_status(job_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    require_member(session, job.case_id, user)
    return JobStatusOut(
        job_id=job.id, case_id=job.case_id, stage=job.stage, progress=job.progress, total_files=job.total_files,
        processed_files=job.processed_files, files=job.files or [], warnings=job.warnings or [], error=job.error,
        created_at=job.created_at, completed_at=job.completed_at,
    )


@router.get("/cases/{case_id}/extractions")
def get_case_extractions(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The rule-based extraction of every document on the case, for debugging the pipeline."""
    require_member(session, case_id, user)
    return _case_extraction(session, case_id).model_dump()


@router.get("/cases/{case_id}/extractions/{doc_id}")
def get_document_extraction(case_id: int, doc_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    document = session.exec(
        select(Document).where(Document.id == doc_id, Document.case_id == case_id)
    ).first()
    if not document or not document.extraction:
        raise HTTPException(404, f"No structured extraction found for document {doc_id}")
    return DocumentExtractionEnvelope.model_validate(document.extraction).model_dump()


@router.get("/cases/{case_id}/documents", response_model=List[Document])
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


# ---------- Results ----------

def _key(name: str) -> str:
    return " ".join(name.casefold().split())


@router.get("/cases/{case_id}/discharge-card", response_model=DischargeCard)
def discharge_card(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """
    The newest discharge summary's card, completed with lab values from test reports and medicines
    from prescriptions uploaded on the same case. Without a discharge summary, the newest other card.
    """
    require_member(session, case_id, user)
    cards = session.exec(
        select(DischargeCard).where(DischargeCard.case_id == case_id).order_by(DischargeCard.id.desc())
    ).all()
    if not cards:
        raise HTTPException(404, "No Discharge Card yet")
    primary = next((c for c in cards if c.data.get("kind", "discharge_summary") == "discharge_summary"), cards[0])
    data = json.loads(json.dumps(primary.data))
    names = {
        "lab_values": {_key(v.get("name", "")) for v in data.get("lab_values", [])},
        "medicines": {_key(m.get("name", "")) for m in data.get("medicines", [])},
    }
    for other in cards:
        if other.id == primary.id:
            continue
        for field in ("lab_values", "medicines"):
            for entry in other.data.get(field, []):
                if _key(entry.get("name", "")) not in names[field]:
                    data.setdefault(field, []).append({**entry, "from_document_id": other.document_id})
                    names[field].add(_key(entry.get("name", "")))
    return DischargeCard(id=primary.id, case_id=case_id, document_id=primary.document_id, data=data,
                         created_at=primary.created_at)


class BillOut(BaseModel):
    total: float
    items: list[BillItem]


@router.get("/cases/{case_id}/bill", response_model=BillOut)
def bill(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    items = session.exec(select(BillItem).where(BillItem.case_id == case_id)).all()
    return BillOut(total=sum(i.amount for i in items), items=items)


@router.get("/cases/{case_id}/policy", response_model=PolicySummary)
def policy(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    stmt = select(PolicySummary).where(PolicySummary.case_id == case_id).order_by(PolicySummary.id.desc())
    found = session.exec(stmt).first()
    if not found:
        raise HTTPException(404, "No insurance policy read yet")
    return found


# ---------- Questions ----------

def _qa_text(session: Session, doc: Document) -> str:
    """The document's own text, or its extracted data when it was read from images."""
    if doc.text and doc.text.strip():
        return doc.text
    cards = session.exec(select(DischargeCard).where(DischargeCard.document_id == doc.id)).all()
    items = session.exec(select(BillItem).where(BillItem.document_id == doc.id)).all()
    policies = session.exec(select(PolicySummary).where(PolicySummary.document_id == doc.id)).all()
    data = (
        [c.data for c in cards]
        + [i.model_dump(include={"description", "amount", "explanation"}) for i in items]
        + [p.data for p in policies]
    )
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
    question_text = (body.question or "").strip()
    if not question_text:
        raise HTTPException(422, "Question cannot be empty.")
    if not settings.groq_api_key.strip():
        raise HTTPException(503, "AI service is not configured. Please set GROQ_API_KEY on the server.")

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
