import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlmodel import Session, select

from ..db import engine, get_session
from ..deps import add_event, current_user, require_member
from ..models import DOC_TYPES, BillItem, DischargeCard, Document, ProcessingJob, User
from ..notify import notify_case
from ..pipeline.runner import parse_recognized_text
from ..pipeline.schemas import DocumentExtractionEnvelope, utc_now_iso

router = APIRouter(tags=["documents"])


class RecognizedPageIn(BaseModel):
    """One page of text produced locally by Android ML Kit."""

    page_number: int = Field(ge=1, le=500)
    text: str = Field(max_length=500_000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class LocalOcrDocumentIn(BaseModel):
    """Document metadata and recognized text; the original file stays on-device."""

    filename: str = Field(min_length=1, max_length=255)
    pages: list[RecognizedPageIn] = Field(min_length=1, max_length=500)
    doc_type: str = "unknown"
    file_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("filename")
    @classmethod
    def clean_filename(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("filename cannot be blank")
        return cleaned

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, value: str) -> str:
        if value not in DOC_TYPES:
            raise ValueError(f"unsupported doc_type: {value}")
        return value

    @model_validator(mode="after")
    def require_recognized_text(self):
        if not any(page.text.strip() for page in self.pages):
            raise ValueError("at least one page must contain recognized text")
        page_numbers = [page.page_number for page in self.pages]
        if len(set(page_numbers)) != len(page_numbers):
            raise ValueError("page_number values must be unique")
        return self

    def formatted_text(self) -> str:
        return "\n\n".join(
            f"[Page {page.page_number}]\n{page.text.strip()}"
            for page in sorted(self.pages, key=lambda item: item.page_number)
        )

    def average_confidence(self) -> float | None:
        values = [page.confidence for page in self.pages if page.confidence is not None]
        return round(sum(values) / len(values), 3) if values else None


class LocalOcrBatchIn(BaseModel):
    documents: list[LocalOcrDocumentIn] = Field(min_length=1, max_length=20)


class DocumentOut(BaseModel):
    """Safe document status response; raw recognized medical text is not returned here."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    doc_type: str
    filename: str
    sha256: str
    status: str
    error: str | None
    classified_type: str | None
    extraction_method: str | None
    created_at: datetime


class SubmissionOut(BaseModel):
    job_id: str
    case_id: int
    documents: list[DocumentOut]


class JobStatusOut(BaseModel):
    job_id: str
    case_id: int
    stage: str
    progress: float
    total_files: int
    processed_files: int
    files: list[dict[str, Any]]
    warnings: list[str]
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


def _persist_structured_views(
    session: Session,
    case_id: int,
    document: Document,
    envelope: DocumentExtractionEnvelope,
) -> None:
    """Populate the existing app-facing tables from deterministic parser output."""
    if envelope.doc_type == "discharge_summary" and envelope.fields:
        follow_up = envelope.fields.get("follow_up") or {}
        card_data = {
            "diagnosis": {
                "name": envelope.fields.get("diagnosis") or "Discharge Diagnosis",
                "plain": "",
                "source_page": 1,
            },
            "medicines": [
                {
                    "name": medicine.get("name") or "",
                    "dose": medicine.get("dose") or "",
                    "schedule": medicine.get("frequency") or "",
                    "days": 7,
                    "purpose": medicine.get("purpose") or "",
                    "source_page": 1,
                }
                for medicine in envelope.fields.get("medicines", [])
            ],
            "lab_values": [],
            "precautions": [
                {"text": advice, "source_page": 1}
                for advice in envelope.fields.get("advice", [])
            ],
            "follow_ups": [
                {
                    "what": follow_up.get("note") or "Follow up",
                    "when": follow_up.get("date") or "",
                    "source_page": 1,
                }
            ],
            "disclaimer": "This explains your documents. It is not medical advice.",
        }
        card = DischargeCard(case_id=case_id, document_id=document.id, data=card_data)
        session.add(card)
        session.flush()
        add_event(session, case_id, "discharge_card", "Discharge Card ready", card.id)
        return

    if envelope.doc_type in ("hospital_bill", "pharmacy_bill", "lab_bill") and envelope.fields:
        for item in envelope.fields.get("line_items", []):
            session.add(
                BillItem(
                    case_id=case_id,
                    document_id=document.id,
                    description=item.get("description") or "Item",
                    amount=float(item.get("amount") or 0.0),
                    explanation="",
                    worth_asking=False,
                )
            )
        add_event(session, case_id, "bill", "Bill processed", document.id)


def execute_job_parsing(job_id: str, case_id: int, doc_ids: list[int]) -> None:
    """Parse already-recognized ML Kit text and persist app-facing records."""
    with Session(engine) as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            return

        input_metadata = {
            item["doc_id"]: item for item in (job.files or []) if item.get("doc_id") is not None
        }
        job.stage = "parsing"
        job.progress = 0.1
        session.add(job)
        session.commit()

        file_statuses: list[dict[str, Any]] = []
        job_warnings = list(job.warnings or [])
        ready_count = 0

        for index, doc_id in enumerate(doc_ids, start=1):
            document = session.get(Document, doc_id)
            if not document:
                continue
            metadata = input_metadata.get(doc_id, {})

            try:
                cached = session.exec(
                    select(Document).where(
                        Document.sha256 == document.sha256,
                        Document.id != document.id,
                        Document.extraction.is_not(None),
                    )
                ).first()
                if cached and cached.extraction:
                    cached_data = dict(cached.extraction)
                    cached_data.update(
                        doc_id=str(document.id),
                        case_id=str(case_id),
                        source_file=document.filename,
                        extracted_at=utc_now_iso(),
                        extraction_method="mlkit",
                        warnings=list(cached_data.get("warnings", []))
                        + ["Structured parsing reused from the database file-hash cache."],
                    )
                    envelope = DocumentExtractionEnvelope(**cached_data)
                else:
                    envelope = parse_recognized_text(
                        case_id=case_id,
                        doc_id=document.id,
                        recognized_text=document.text or "",
                        file_hash=document.sha256,
                        source_filename=document.filename,
                        hint_doc_type=document.doc_type,
                        page_count=int(metadata.get("page_count") or 1),
                        extraction_confidence=metadata.get("confidence"),
                        input_warnings=list(metadata.get("warnings") or []),
                    )

                document.status = "ready"
                document.error = None
                document.doc_type = envelope.doc_type
                document.classified_type = envelope.doc_type
                document.extraction_method = "mlkit"
                document.extraction = envelope.model_dump(mode="json")
                _persist_structured_views(session, case_id, document, envelope)
                ready_count += 1

                if envelope.warnings:
                    job_warnings.extend(
                        f"[{document.filename}] {warning}" for warning in envelope.warnings
                    )
                file_statuses.append(
                    {
                        "doc_id": document.id,
                        "filename": document.filename,
                        "status": "ready",
                        "doc_type": envelope.doc_type,
                        "pages": envelope.pages,
                        "extraction_method": "mlkit",
                        "warnings": envelope.warnings,
                    }
                )
            except Exception as error:
                document.status = "failed"
                document.error = str(error)
                file_statuses.append(
                    {
                        "doc_id": document.id,
                        "filename": document.filename,
                        "status": "failed",
                        "error": str(error),
                    }
                )
                job_warnings.append(f"Failed parsing {document.filename}: {error}")

            session.add(document)
            job.processed_files = index
            job.files = file_statuses
            job.warnings = job_warnings
            job.progress = round(0.1 + index / max(len(doc_ids), 1) * 0.85, 2)
            session.add(job)
            session.commit()

        job.stage = "completed" if ready_count else "failed"
        job.progress = 1.0
        if not ready_count:
            job.error = "No recognized document text could be parsed."
        job.completed_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()

        if ready_count:
            notify_case(session, case_id, "MedSure", "Your documents are ready.", "document")


@router.post("/cases/{case_id}/documents", response_model=SubmissionOut, status_code=202)
def submit_local_ocr_results(
    case_id: int,
    body: LocalOcrBatchIn,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """Accept text produced on-device by ML Kit. No files or cloud OCR are accepted."""
    require_member(session, case_id, user)
    documents: list[Document] = []
    job_files: list[dict[str, Any]] = []

    for incoming in body.documents:
        recognized_text = incoming.formatted_text()
        digest = (incoming.file_hash or hashlib.sha256(recognized_text.encode("utf-8")).hexdigest()).lower()
        document = Document(
            case_id=case_id,
            doc_type=incoming.doc_type,
            filename=incoming.filename,
            path="",
            sha256=digest,
            text=recognized_text,
            status="processing",
            extraction_method="mlkit",
        )
        session.add(document)
        session.flush()
        add_event(session, case_id, "document", f"Received {incoming.filename}", document.id)
        documents.append(document)
        job_files.append(
            {
                "doc_id": document.id,
                "filename": document.filename,
                "status": "queued",
                "page_count": len(incoming.pages),
                "confidence": incoming.average_confidence(),
                "warnings": incoming.warnings,
            }
        )

    job_id = uuid.uuid4().hex
    job = ProcessingJob(
        id=job_id,
        case_id=case_id,
        stage="queued",
        progress=0.05,
        total_files=len(documents),
        processed_files=0,
        files=job_files,
        warnings=[],
    )
    session.add(job)
    session.commit()
    for document in documents:
        session.refresh(document)

    background.add_task(execute_job_parsing, job_id, case_id, [document.id for document in documents])
    return SubmissionOut(job_id=job_id, case_id=case_id, documents=documents)


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job_status(
    job_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
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
def get_case_extractions(
    case_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    documents = session.exec(
        select(Document).where(Document.case_id == case_id).order_by(Document.created_at)
    ).all()
    extractions = [document.extraction for document in documents if document.extraction]
    return {
        "schema_version": "1.0.0",
        "case_id": str(case_id),
        "total_documents": len(extractions),
        "documents": extractions,
    }


@router.get("/cases/{case_id}/extractions/{doc_id}")
def get_document_extraction(
    case_id: int,
    doc_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    document = session.get(Document, doc_id)
    if not document or document.case_id != case_id or not document.extraction:
        raise HTTPException(404, f"No structured extraction found for document {doc_id}")
    return document.extraction


@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
def list_documents(
    case_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    return session.exec(select(Document).where(Document.case_id == case_id)).all()


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(
    doc_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    document = session.get(Document, doc_id)
    if not document:
        raise HTTPException(404, "Document not found")
    require_member(session, document.case_id, user)
    return document


@router.get("/cases/{case_id}/discharge-card", response_model=DischargeCard)
def discharge_card(
    case_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    statement = (
        select(DischargeCard)
        .where(DischargeCard.case_id == case_id)
        .order_by(DischargeCard.id.desc())
    )
    card = session.exec(statement).first()
    if not card:
        raise HTTPException(404, "No Discharge Card yet")
    return card


class BillOut(BaseModel):
    total: float
    items: list[BillItem]


@router.get("/cases/{case_id}/bill", response_model=BillOut)
def bill(
    case_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    require_member(session, case_id, user)
    items = session.exec(select(BillItem).where(BillItem.case_id == case_id)).all()
    return BillOut(total=sum(item.amount for item in items), items=items)
