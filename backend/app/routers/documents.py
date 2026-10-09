import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import engine, get_session
from ..deps import add_event, current_user, require_member
from ..models import DOC_TYPES, BillItem, DischargeCard, Document, ProcessingJob, User
from ..notify import notify_case
from ..pipeline.runner import run_pipeline_for_document
from ..pipeline.storage import (
    get_case_dir,
    load_document_extraction,
    update_case_merged_extraction,
)

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


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


def execute_job_processing(job_id: str, case_id: int, doc_ids: List[int]) -> None:
    """
    Background worker function that runs the extraction pipeline for each document in the job.
    Updates job progress and per-file status incrementally without blocking HTTP requests.
    """
    with Session(engine) as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            return

        job.stage = "extracting"
        job.progress = 0.2
        session.add(job)
        session.commit()

        job_files_status = list(job.files or [])
        job_warnings = list(job.warnings or [])

        for idx, doc_id in enumerate(doc_ids, start=1):
            doc = session.get(Document, doc_id)
            if not doc:
                continue

            try:
                # Stage: Extracting / Classifying / Parsing
                job.stage = "classifying"
                job.progress = round(0.2 + (idx - 0.5) / max(len(doc_ids), 1) * 0.7, 2)
                session.add(job)
                session.commit()

                envelope = run_pipeline_for_document(
                    case_id=case_id,
                    doc_id=doc.id,
                    file_path=doc.path,
                    file_hash=doc.sha256,
                    source_filename=doc.filename,
                    hint_doc_type=doc.doc_type,
                )

                # Update document status and classified type in DB
                doc.status = "ready"
                doc.doc_type = envelope.doc_type
                if envelope.warnings:
                    job_warnings.extend([f"[{doc.filename}] {w}" for w in envelope.warnings])

                # Update legacy DischargeCard and BillItem tables if applicable
                if envelope.doc_type == "discharge_summary" and envelope.fields:
                    card_data = {
                        "diagnosis": {"name": envelope.fields.get("diagnosis") or "Discharge Diagnosis", "plain": "", "source_page": 1},
                        "medicines": [
                            {"name": m.get("name") or "", "dose": m.get("dose") or "", "schedule": m.get("frequency") or "", "days": 7, "purpose": m.get("purpose") or "", "source_page": 1}
                            for m in envelope.fields.get("medicines", [])
                        ],
                        "lab_values": [],
                        "precautions": [{"text": a, "source_page": 1} for a in envelope.fields.get("advice", [])],
                        "follow_ups": [{"what": envelope.fields.get("follow_up", {}).get("note") or "Follow up", "when": envelope.fields.get("follow_up", {}).get("date") or "", "source_page": 1}],
                        "disclaimer": "This explains your documents. It is not medical advice.",
                    }
                    card = DischargeCard(case_id=case_id, document_id=doc.id, data=card_data)
                    session.add(card)
                    session.flush()
                    add_event(session, case_id, "discharge_card", "Discharge Card ready", card.id)

                elif envelope.doc_type in ("hospital_bill", "pharmacy_bill", "lab_bill") and envelope.fields:
                    for item in envelope.fields.get("line_items", []):
                        session.add(
                            BillItem(
                                case_id=case_id,
                                document_id=doc.id,
                                description=item.get("description") or "Item",
                                amount=float(item.get("amount") or 0.0),
                                explanation="",
                                worth_asking=False,
                            )
                        )
                    add_event(session, case_id, "bill", "Bill processed", doc.id)

                job_files_status.append({
                    "doc_id": doc.id,
                    "filename": doc.filename,
                    "status": "ready",
                    "doc_type": envelope.doc_type,
                    "pages": envelope.pages,
                    "extraction_method": envelope.extraction_method,
                    "warnings": envelope.warnings,
                })

            except Exception as e:
                doc.status = "failed"
                doc.error = str(e)
                job_files_status.append({
                    "doc_id": doc.id,
                    "filename": doc.filename,
                    "status": "failed",
                    "error": str(e),
                })
                job_warnings.append(f"Failed processing {doc.filename}: {str(e)}")

            session.add(doc)
            job.processed_files = idx
            job.files = job_files_status
            job.warnings = job_warnings
            job.progress = round(0.2 + (idx / max(len(doc_ids), 1)) * 0.75, 2)
            session.add(job)
            session.commit()

        # Finalize job
        job.stage = "completed"
        job.progress = 1.0
        job.completed_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()

        # Update case-level merged extraction JSON on disk
        update_case_merged_extraction(case_id)


@router.post("/cases/{case_id}/documents", response_model=UploadResultOut, status_code=202)
async def upload_documents(
    case_id: int,
    background: BackgroundTasks,
    files: List[UploadFile] = File(default=[]),
    file: Optional[UploadFile] = File(None),
    doc_type: Optional[str] = Form(None),
    ocr_text: Optional[str] = Form(None),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)

    # Collect all uploaded files (single or multiple)
    upload_list: List[UploadFile] = []
    if file:
        upload_list.append(file)
    if files:
        for f in files:
            if f and f.filename and f not in upload_list:
                upload_list.append(f)

    ocr_text = (ocr_text or "").strip() or None
    if not upload_list and not ocr_text:
        raise HTTPException(422, "Please provide at least one file or ocr_text to upload.")

    created_docs: List[Document] = []
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)

    # Process each uploaded file
    for up_file in upload_list:
        fname = up_file.filename or "uploaded_doc"
        ext = Path(fname).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file extension '{ext}'. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}")

        data = await up_file.read()

        if len(data) > settings.upload_max_size_bytes:
            limit_mb = settings.upload_max_size_bytes / (1024 * 1024)
            raise HTTPException(413, f"File '{fname}' exceeds the maximum upload limit of {limit_mb:.1f} MB.")

        digest = hashlib.sha256(data).hexdigest()
        saved_file = folder / f"{digest}{ext}"
        saved_file.write_bytes(data)

        # Validate doc_type hint if provided
        final_doc_type = doc_type if (doc_type and doc_type in DOC_TYPES) else "unknown"

        doc = Document(
            case_id=case_id,
            doc_type=final_doc_type,
            filename=fname,
            path=str(saved_file),
            sha256=digest,
            text=None,
            status="processing",
        )
        session.add(doc)
        session.flush()
        add_event(session, case_id, "document", f"Uploaded {fname}", doc.id)
        created_docs.append(doc)

    # If only ocr_text was provided without files
    if not upload_list and ocr_text:
        data = ocr_text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        saved_file = folder / f"{digest}.txt"
        saved_file.write_bytes(data)

        final_doc_type = doc_type if (doc_type and doc_type in DOC_TYPES) else "unknown"
        doc = Document(
            case_id=case_id,
            doc_type=final_doc_type,
            filename="ocr_text.txt",
            path=str(saved_file),
            sha256=digest,
            text=ocr_text,
            status="processing",
        )
        session.add(doc)
        session.flush()
        created_docs.append(doc)

    session.commit()
    for d in created_docs:
        session.refresh(d)

    # Create a processing job for tracking
    job_id = uuid.uuid4().hex
    job = ProcessingJob(
        id=job_id,
        case_id=case_id,
        stage="uploading",
        progress=0.1,
        total_files=len(created_docs),
        processed_files=0,
        files=[{"doc_id": d.id, "filename": d.filename, "status": "processing"} for d in created_docs],
        warnings=[],
    )
    session.add(job)
    session.commit()

    # Queue background processing
    doc_ids = [d.id for d in created_docs]
    background.add_task(execute_job_processing, job_id, case_id, doc_ids)

    return UploadResultOut(job_id=job_id, case_id=case_id, documents=created_docs)


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job_status(job_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    require_member(session, job.case_id, user)
    return JobStatusOut(
        job_id=job.id,
        case_id=job.case_id,
        stage=job.stage,
        progress=job.progress,
        total_files=job.total_files,
        processed_files=job.processed_files,
        files=job.files or [],
        warnings=job.warnings or [],
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/cases/{case_id}/extractions")
def get_case_extractions(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Retrieves all extractions for a case from disk/merged JSON."""
    require_member(session, case_id, user)
    merged_envelope = update_case_merged_extraction(case_id)
    return merged_envelope.model_dump()


@router.get("/cases/{case_id}/extractions/{doc_id}")
def get_document_extraction(case_id: int, doc_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Retrieves one document's structured extraction JSON."""
    require_member(session, case_id, user)
    extraction = load_document_extraction(case_id, doc_id)
    if not extraction:
        raise HTTPException(404, f"No structured extraction found for document {doc_id}")
    return extraction.model_dump()


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
    items: List[BillItem]


@router.get("/cases/{case_id}/bill", response_model=BillOut)
def bill(case_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    require_member(session, case_id, user)
    items = session.exec(select(BillItem).where(BillItem.case_id == case_id)).all()
    return BillOut(total=sum(i.amount for i in items), items=items)
