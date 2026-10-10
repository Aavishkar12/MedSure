from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Case, CaseMember, DischargeCard, Document, ProcessingJob, User
from app.routers import documents as document_routes


DISCHARGE_TEXT = """
SUNSHINE HEART HOSPITAL
DISCHARGE SUMMARY
Patient: Lakshmi Narayanan Age: 68 Y Sex: Female
UHID: SHH-204518 IP No: IP/26/09/0731
Date of Admission: 23-09-2026 Date of Discharge: 28-09-2026
Diagnosis: Acute Decompensated Heart Failure
MEDICATIONS:
1. Tab Furosemide 40 mg OD
2. Tab Metoprolol 25 mg BD
Follow-up: 05-10-2026 at 10:30 AM
"""


def test_mlkit_text_persists_extraction_and_populates_discharge_card(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "pipeline.db"
    test_engine = create_engine(
        f"sqlite:///{database_path.as_posix()}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(document_routes, "engine", test_engine)

    with Session(test_engine) as session:
        user = User(id="patient", name="Lakshmi", phone="9876500001")
        case = Case(patient_name="Lakshmi", created_by=user.id)
        session.add(user)
        session.add(case)
        session.flush()
        session.add(CaseMember(case_id=case.id, user_id=user.id, relation="self"))
        document = Document(
            case_id=case.id,
            doc_type="discharge_summary",
            filename="discharge.txt",
            path="",
            sha256="test-hash",
            text=DISCHARGE_TEXT,
        )
        session.add(document)
        session.flush()
        job = ProcessingJob(
            id="job-1",
            case_id=case.id,
            total_files=1,
            files=[{
                "doc_id": document.id,
                "filename": document.filename,
                "status": "queued",
                "page_count": 1,
                "confidence": 0.94,
                "warnings": [],
            }],
        )
        session.add(job)
        session.commit()
        case_id, document_id = case.id, document.id

    document_routes.execute_job_parsing("job-1", case_id, [document_id])

    with Session(test_engine) as session:
        document = session.get(Document, document_id)
        job = session.get(ProcessingJob, "job-1")
        card = session.exec(
            select(DischargeCard).where(DischargeCard.document_id == document_id)
        ).one()
        extracted = document_routes.get_case_extractions(case_id, session.get(User, "patient"), session)

        assert document.status == "ready"
        assert document.classified_type == "discharge_summary"
        assert document.extraction_method == "mlkit"
        assert document.path == ""
        assert document.extraction["fields"]["patient"]["name"] == "Lakshmi Narayanan"
        assert document.extraction["extraction_confidence"] == 0.94
        assert job.stage == "completed"
        assert job.progress == 1.0
        assert card.data["medicines"][0]["name"] == "Furosemide"
        assert extracted["total_documents"] == 1
        assert extracted["documents"][0]["doc_id"] == str(document_id)

    test_engine.dispose()


def test_local_ocr_contract_rejects_blank_pages():
    with pytest.raises(ValidationError, match="at least one page must contain recognized text"):
        document_routes.LocalOcrDocumentIn(
            filename="blank.jpg",
            pages=[document_routes.RecognizedPageIn(page_number=1, text="   ")],
        )
