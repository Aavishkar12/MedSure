"""Reading happens on the phone (ML Kit) or from a PDF's own text layer. The server never reads page
images and never sends them anywhere: the text is saved in the database and only that text goes to the AI."""

import inspect
import json
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import llm
from app.config import settings
from app.db import engine, init_db
from app.main import app
from app.models import Document
from app.pipeline.extractor import NEEDS_PHONE_TEXT, extract_document_text

HEADERS = {"x-user-id": "local-ocr-user"}


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    settings.auth_dev_bypass = True
    init_db()

PHONE_TEXT = "[Page 1]\nDISCHARGE SUMMARY\nDiagnosis: Hypertension\nTab. Amlodipine 5 mg once daily for 30 days"
CARD = {
    "diagnosis": {"name": "Hypertension", "plain": "High blood pressure", "source_page": 1},
    "medicines": [{"name": "Amlodipine", "dose": "5 mg", "schedule": "once daily", "purpose": "Lowers blood pressure", "source_page": 1}],
    "lab_values": [], "precautions": [], "follow_ups": [],
}


def _jpeg(width: int = 200) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=width, height=100)
    return page.get_pixmap().tobytes("jpeg")


def _pdf(pages: list[str]) -> bytes:
    """A PDF where each entry is the typed text of a page; an empty entry is a page with no text (a scan)."""
    pdf = pymupdf.open()
    for text in pages:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
    return pdf.tobytes()


def _case(client: TestClient) -> int:
    return client.post("/cases", json={"patient_name": "Local OCR"}, headers=HEADERS).json()["id"]


def test_no_function_can_send_images_to_the_ai():
    assert "images" not in inspect.signature(llm.complete_json).parameters
    for fn in (llm.extract_discharge_card, llm.extract_bill, llm.extract_prescription, llm.extract_lab_report, llm.extract_policy):
        assert list(inspect.signature(fn).parameters) == ["text"]
    assert not hasattr(llm, "file_to_images")
    assert not hasattr(settings, "groq_vision_model") and not hasattr(settings, "tesseract_cmd")


def test_photo_with_phone_text_is_saved_then_sent_to_the_ai_as_text_only():
    client = TestClient(app)
    case_id = _case(client)
    sent = []

    def fake_chat(**kwargs):
        sent.append(kwargs)
        return json.dumps(CARD)

    with patch("fastapi.BackgroundTasks.add_task"):
        up = client.post(
            f"/cases/{case_id}/documents", headers=HEADERS,
            data={"doc_type": "discharge_summary", "ocr_text": PHONE_TEXT},
            files={"file": ("photo.jpg", _jpeg(), "image/jpeg")},
        )
    assert up.status_code == 202
    doc_id = up.json()["documents"][0]["id"]

    # The phone's text is in the database before anything is processed.
    with Session(engine) as session:
        assert session.get(Document, doc_id).text == PHONE_TEXT

    from app.routers.documents import process_document

    with patch("app.llm.client._chat", side_effect=fake_chat), patch.object(settings, "groq_api_key", "test-key"):
        process_document(doc_id)

    doc = client.get(f"/documents/{doc_id}", headers=HEADERS).json()
    assert doc["status"] == "ready", doc
    assert len(sent) == 1
    for message in sent[0]["messages"]:
        assert isinstance(message["content"], str)  # plain text: no image parts
    assert "Amlodipine 5 mg once daily" in sent[0]["messages"][1]["content"]
    assert sent[0]["model"] == settings.groq_text_model
    ext = client.get(f"/cases/{case_id}/extractions/{doc_id}", headers=HEADERS).json()
    assert ext["extraction_method"] == "device_ocr"
    card = client.get(f"/cases/{case_id}/discharge-card", headers=HEADERS).json()["data"]
    assert card["medicines"][0]["name"] == "Amlodipine"


def test_photo_without_phone_text_fails_with_a_clear_message_and_calls_nothing():
    client = TestClient(app)
    case_id = _case(client)
    with patch("app.llm.client._chat") as chat, patch.object(settings, "groq_api_key", "test-key"):
        up = client.post(
            f"/cases/{case_id}/documents", headers=HEADERS,
            # a different picture from the test above: an identical file would be answered from the cache
            data={"doc_type": "discharge_summary"}, files={"file": ("other.jpg", _jpeg(260), "image/jpeg")},
        )
        doc = client.get(f"/documents/{up.json()['documents'][0]['id']}", headers=HEADERS).json()
    assert doc["status"] == "failed" and doc["error"] == NEEDS_PHONE_TEXT
    chat.assert_not_called()


def test_typed_pdf_uses_its_own_text_even_when_the_phone_sent_text(tmp_path):
    path = tmp_path / "typed.pdf"
    path.write_bytes(_pdf(["Discharge summary. Diagnosis: Hypertension. Amlodipine 5 mg daily."]))
    result = extract_document_text(str(path), "[Page 1]\nD1scharge 5ummary. Diagn0sis: Hypertensi0n. Aml0dipine")
    assert result.primary_method == "text_layer"
    assert "Diagnosis: Hypertension" in result.full_text and "Diagn0sis" not in result.full_text


def test_scanned_pdf_uses_the_phone_text_for_every_page(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf(["", "", ""]))
    phone = "\n\n".join(f"[Page {i}]\nDischarge summary page {i} with enough words to count" for i in (1, 2, 3))
    result = extract_document_text(str(path), phone)
    assert result.primary_method == "device_ocr" and result.page_count == 3
    assert "[Page 3]" in result.full_text

    nothing = extract_document_text(str(path), None)
    assert nothing.full_text == "" and NEEDS_PHONE_TEXT in nothing.warnings


def test_partly_scanned_pdf_keeps_typed_pages_when_the_phone_sent_nothing(tmp_path):
    path = tmp_path / "mixed.pdf"
    path.write_bytes(_pdf(["Final bill. Room rent 5 days 30000. Pharmacy 4200. Total 34200.", ""]))
    result = extract_document_text(str(path), None)
    assert result.primary_method == "text_layer" and "Room rent" in result.full_text
    assert any("Page 2" in w for w in result.warnings)
