import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.db import get_session
from app.models import User, Case, CaseMember, Document, DischargeCard, BillItem
from app.deps import current_user
from app.config import settings
from app import llm


# Setup in-memory test database
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    # Mock authenticated user
    test_user = User(id="user_test_123", phone="9876543210", email="test@medsure.app", name="Test User")
    session.add(test_user)
    session.commit()

    def get_session_override():
        return session

    def current_user_override():
        return test_user

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[current_user] = current_user_override

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="test_case")
def test_case_fixture(session: Session):
    user = session.get(User, "user_test_123")
    c = Case(patient_name="Lakshmi Devi", created_by=user.id)
    session.add(c)
    session.commit()
    session.refresh(c)

    m = CaseMember(case_id=c.id, user_id=user.id, relation="self", can_approve=True)
    session.add(m)
    session.commit()
    return c


# ==================== LLM UNIT TESTS ====================

def test_extract_discharge_card_success():
    mock_payload = {
        "diagnosis": {
            "name": "Congestive Heart Failure (NYHA Class II)",
            "plain": "The heart muscle was pumping less effectively, leading to fluid retention.",
            "source_page": 1,
        },
        "medicines": [
            {
                "name": "Furosemide",
                "dose": "40 mg",
                "schedule": "Once daily in morning",
                "purpose": "Water pill to reduce swelling and fluid build-up",
                "flag": None,
                "source_page": 2,
            }
        ],
        "lab_values": [
            {
                "name": "Serum Potassium",
                "value": "4.2",
                "unit": "mEq/L",
                "range": "3.5 - 5.0",
                "status": "normal",
                "plain": "Potassium level is within normal healthy limits.",
                "source_page": 2,
            }
        ],
        "precautions": [{"text": "Monitor daily weight every morning before breakfast.", "source_page": 3}],
        "follow_ups": [{"what": "Cardiology OPD review with repeat electrolytes", "when": "After 7 days", "source_page": 3}],
        "disclaimer": "This explains your documents. It is not medical advice.",
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        result = llm.extract_discharge_card("[Page 2]\nSerum Potassium 4.2 mEq/L (3.5 - 5.0)\nDischarge medicines: Tab Furosemide 40 mg once daily in morning")
        assert result["diagnosis"]["name"] == "Congestive Heart Failure (NYHA Class II)"
        assert len(result["medicines"]) == 1
        assert result["medicines"][0]["name"] == "Furosemide"
        assert result["lab_values"][0]["status"] == "normal"


def test_discharge_card_drops_medicines_not_in_document():
    """The model must not add a medicine the report does not mention (e.g. one from a typical treatment)."""
    mock_payload = {
        "summary": "Admitted with fluid on the lungs; treated and discharged stable.",
        "diagnosis": {"name": "Heart failure", "plain": "The heart was not pumping strongly enough.", "source_page": 1},
        "medicines": [
            {"name": "Tab Furosemide", "dose": "40 mg", "schedule": "once a day", "source_page": 1},
            {"name": "Pantoprazole", "dose": "40 mg", "schedule": "before breakfast", "source_page": 1},
        ],
        "lab_values": [
            {"name": "Hb", "value": "11.2", "unit": "g/dL", "status": "low"},
            {"name": "Creatinine", "value": "2.1", "unit": "mg/dL", "status": "high"},
        ],
        "warning_signs": [{"text": "Weight gain over 2 kg in 3 days", "source_page": 1}],
    }
    text = "[Page 1]\nDiagnosis: Heart failure\nHb 11.2 g/dL\nDischarge medication: Tab. Furosemide 40mg OD"
    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        card = llm.extract_discharge_card(text)
    assert [m["name"] for m in card["medicines"]] == ["Tab Furosemide"]
    assert [lab["name"] for lab in card["lab_values"]] == ["Hb"]
    assert card["summary"].startswith("Admitted")
    assert card["warning_signs"][0]["text"].startswith("Weight gain")


def test_extract_bill_reconciliation_math():
    mock_payload = {
        "hospital_name": "Apollo Hospitals",
        "invoice_number": "INV-2026-991",
        "invoice_date": "2026-10-01",
        "items": [
            {"description": "Room Charges (5 days)", "amount": 20000.0, "quantity": 5.0, "unit_price": 4000.0, "explanation": "Room fee", "worth_asking": False, "concept": "room_and_nursing"},
            {"description": "Specialist Consultation", "amount": 3000.0, "quantity": 2.0, "unit_price": 1500.0, "explanation": "Doctor fee", "worth_asking": False, "concept": "medicines"},
        ],
        "total_billed": 23000.0,
        "patient_payable": 23000.0,
        "discrepancy_note": None,
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        items = llm.extract_bill("Bill text...")
        assert len(items) == 2
        assert items[0]["description"] == "Room Charges (5 days)"
        assert items[0]["amount"] == 20000.0
        assert items[1]["amount"] == 3000.0


def test_extract_prescription():
    mock_payload = {
        "doctor_name": "Dr. Sharma",
        "date": "2026-09-28",
        "medicines": [
            {
                "medicine_name": "Metoprolol Succinate",
                "strength": "25 mg",
                "form": "Tablet",
                "dosage_frequency": "1 tablet once daily with food",
                "duration": "30 days",
                "instructions": "Do not skip doses",
                "flag_for_confirmation": False,
                "source_page": 1,
            }
        ],
        "general_advice": ["Take after breakfast"],
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        result = llm.extract_prescription("Rx: Tab Metoprolol Succinate 25 mg once daily x 30 days")
        assert result["doctor_name"] == "Dr. Sharma"
        assert len(result["medicines"]) == 1
        assert result["medicines"][0]["medicine_name"] == "Metoprolol Succinate"


def test_extract_lab_report():
    mock_payload = {
        "lab_name": "SRL Diagnostics",
        "collection_date": "2026-09-29",
        "results": [
            {
                "test_name": "Hemoglobin",
                "value": "11.2",
                "unit": "g/dL",
                "reference_range": "12.0 - 15.5",
                "flag": "low",
                "plain_explanation": "Slightly lower than usual reference range. Discuss with doctor.",
                "source_page": 1,
            }
        ],
        "summary": "Sample processed normally",
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        result = llm.extract_lab_report("Lab report text...")
        assert len(result["results"]) == 1
        assert result["results"][0]["flag"] == "low"
        assert result["results"][0]["test_name"] == "Hemoglobin"


def test_extract_policy():
    mock_payload = {
        "insurer": "Star Health",
        "policy_number": "POL-98765432",
        "policyholder_name": "Lakshmi Devi",
        "sum_insured": "500000",
        "copay": "10%",
        "exclusions": ["Pre-existing conditions waiting period of 2 years"],
        "preauth_requirement": "Required 48 hours before planned admission",
        "claim_submission_deadline": "Within 15 days of discharge",
        "source_page": 1,
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        result = llm.extract_policy("Insurance policy text...")
        assert result["insurer"] == "Star Health"
        assert result["sum_insured"] == 500000.0
        assert len(result["exclusions"]) == 1


def test_qa_grounded_answer():
    mock_payload = {
        "answer": "You should take Furosemide 40 mg once daily in the morning to prevent swelling.",
        "sources": [
            {"document_id": 1, "document_type": "discharge_summary", "page": 2, "quote": "Furosemide 40 mg once daily in morning"}
        ],
        "grounded": True,
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_payload)):
        ans = llm.answer_question("When should I take Furosemide?", [{"id": 1, "doc_type": "discharge_summary", "text": "Furosemide 40 mg once daily in morning"}])
        assert ans["grounded"] is True
        assert "Furosemide" in ans["answer"]
        assert len(ans["sources"]) == 1
        assert ans["sources"][0]["quote"] == "Furosemide 40 mg once daily in morning"


# ==================== ROUTE & API TESTS ====================

def test_upload_file_validation_oversized(client: TestClient, test_case: Case):
    huge_bytes = b"x" * (2 * 1024 * 1024)
    with patch.object(settings, "upload_max_size_bytes", 1024 * 1024):
        response = client.post(
            f"/cases/{test_case.id}/documents",
            data={"doc_type": "discharge_summary"},
            files={"file": ("huge.pdf", huge_bytes, "application/pdf")},
        )
    assert response.status_code == 413
    assert "exceeds the maximum upload size" in response.json()["detail"]


def test_upload_file_validation_empty(client: TestClient, test_case: Case):
    response = client.post(
        f"/cases/{test_case.id}/documents",
        data={"doc_type": "discharge_summary"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_upload_file_validation_invalid_extension(client: TestClient, test_case: Case):
    response = client.post(
        f"/cases/{test_case.id}/documents",
        data={"doc_type": "discharge_summary"},
        files={"file": ("bad.exe", b"binarycontent", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file" in response.json()["detail"]


def test_ask_empty_question(client: TestClient, test_case: Case):
    with patch.object(settings, "groq_api_key", "test-key-123"):
        response = client.post(
            f"/cases/{test_case.id}/ask",
            json={"question": "   "},
        )
        assert response.status_code == 422


def test_ask_no_documents_ready(client: TestClient, test_case: Case):
    with patch.object(settings, "groq_api_key", "test-key-123"):
        response = client.post(
            f"/cases/{test_case.id}/ask",
            json={"question": "What is my diagnosis?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["grounded"] is False
        assert "No readable documents" in data["answer"]


def test_discharge_card_404_when_none(client: TestClient, test_case: Case):
    response = client.get(f"/cases/{test_case.id}/discharge-card")
    assert response.status_code == 404


def test_end_to_end_discharge_card_flow(client: TestClient, test_case: Case, session: Session):
    from app.routers.documents import process_document

    mock_card = {
        "diagnosis": {"name": "Hypertension", "plain": "High blood pressure", "source_page": 1},
        "medicines": [{"name": "Amlodipine", "dose": "5mg", "schedule": "Once daily", "purpose": "Lowers BP", "source_page": 1}],
        "lab_values": [],
        "precautions": [{"text": "Low salt diet", "source_page": 1}],
        "follow_ups": [],
        "disclaimer": "This explains your documents.",
    }

    # Upload document (prevent default background worker from racing)
    with patch("fastapi.BackgroundTasks.add_task"):
        resp = client.post(
            f"/cases/{test_case.id}/documents",
            data={"doc_type": "discharge_summary", "ocr_text": "Patient diagnosed with Hypertension. Prescribed Amlodipine 5mg."},
            files={"file": ("report.pdf", b"%PDF-1.4 dummy discharge summary", "application/pdf")},
        )
    assert resp.status_code == 202
    doc_id = resp.json()["documents"][0]["id"]

    # Process document using test session
    with patch("app.llm.client._chat", return_value=json.dumps(mock_card)), \
         patch.object(settings, "groq_api_key", "test-key-123"):
        process_document(doc_id, session=session)

    # Check status is ready
    status_resp = client.get(f"/documents/{doc_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "ready"

    # Get discharge card
    card_resp = client.get(f"/cases/{test_case.id}/discharge-card")
    assert card_resp.status_code == 200
    card_data = card_resp.json()["data"]
    assert card_data["diagnosis"]["name"] == "Hypertension"
    assert card_data["medicines"][0]["name"] == "Amlodipine"


def test_end_to_end_bill_flow(client: TestClient, test_case: Case, session: Session):
    from app.routers.documents import process_document

    mock_bill = {
        "hospital_name": "Fortis Hospital",
        "invoice_number": "INV-100",
        "items": [
            {"description": "Consultation", "amount": 1500.0, "quantity": 1.0, "unit_price": 1500.0, "explanation": "Doctor fee", "worth_asking": False, "concept": "medicines"},
            {"description": "Blood Test", "amount": 800.0, "quantity": 1.0, "unit_price": 800.0, "explanation": "CBC test", "worth_asking": False, "concept": "blood_count"},
        ],
        "total_billed": 2300.0,
        "patient_payable": 2300.0,
    }

    with patch("fastapi.BackgroundTasks.add_task"):
        resp = client.post(
            f"/cases/{test_case.id}/documents",
            data={"doc_type": "bill", "ocr_text": "Fortis Hospital invoice 100: Consultation 1500, Blood test 800."},
            files={"file": ("bill.pdf", b"%PDF-1.4 dummy bill content", "application/pdf")},
        )
    assert resp.status_code == 202
    doc_id = resp.json()["documents"][0]["id"]

    with patch("app.llm.client._chat", return_value=json.dumps(mock_bill)), \
         patch.object(settings, "groq_api_key", "test-key-123"):
        process_document(doc_id, session=session)

    bill_resp = client.get(f"/cases/{test_case.id}/bill")
    assert bill_resp.status_code == 200
    bill_data = bill_resp.json()
    assert bill_data["total"] == 2300.0
    assert len(bill_data["items"]) == 2


def test_ask_with_ready_documents(client: TestClient, test_case: Case, session: Session):
    # Setup ready document
    doc = Document(
        case_id=test_case.id,
        doc_type="discharge_summary",
        filename="discharge.pdf",
        path="uploads/discharge.pdf",
        sha256="abc1234567890",
        status="ready",
        text="Discharge Summary: Patient Lakshmi Devi. Take Metoprolol 25mg daily.",
    )
    session.add(doc)
    session.commit()

    mock_qa = {
        "answer": "You should take Metoprolol 25mg daily.",
        "sources": [{"document_id": doc.id, "document_type": "discharge_summary", "page": 1, "quote": "Take Metoprolol 25mg daily."}],
        "grounded": True,
    }

    with patch("app.llm.client._chat", return_value=json.dumps(mock_qa)), \
         patch.object(settings, "groq_api_key", "test-key-123"):
        resp = client.post(
            f"/cases/{test_case.id}/ask",
            json={"question": "What dose of Metoprolol was prescribed?"},
        )
        assert resp.status_code == 200
        ans = resp.json()
        assert ans["grounded"] is True
        assert "Metoprolol" in ans["answer"]
        assert len(ans["sources"]) == 1

