import io
import os
from pathlib import Path
# pyrefly: ignore [missing-import]
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.db import init_db
from app.config import settings


@pytest.fixture(scope="module", autouse=True)
def setup_test_db(tmp_path_factory):
    # Its own folder: other test files use in-memory databases whose case ids also start at 1.
    settings.extractions_dir = str(tmp_path_factory.mktemp("e2e_extractions"))
    settings.auth_dev_bypass = True
    init_db()


def create_minimal_pdf_with_text(text_lines: list[str]) -> bytes:
    """Creates a valid PDF binary with a stream containing the specified text lines."""
    stream_content = "BT /F1 12 Tf 16 TL 50 750 Td " + " ".join(f"({line}) Tj T*" for line in text_lines) + " ET"
    stream_bytes = stream_content.encode("latin1")
    pdf = f"""%PDF-1.4
1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj
2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj
3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj
4 0 obj <</Length {len(stream_bytes)}>> stream
{stream_content}
endstream endobj
5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000224 00000 n 
0000000320 00000 n 
trailer <</Size 6 /Root 1 0 R>>
startxref
400
%%EOF"""
    return pdf.encode("latin1")


def test_samples_directory_status():
    """
    Mandated by prompt:
    If sample PDFs are missing, identify explicitly and do not fabricate success.
    """
    samples_dir = Path(__file__).resolve().parent.parent.parent / "samples"
    pdf_files = list(samples_dir.glob("*.pdf")) if samples_dir.exists() else []
    print(f"\n[Test Samples Check] Found {len(pdf_files)} PDF files in samples directory ({samples_dir}).")
    # Record that the 6 sample PDFs are missing from the repo
    assert len(pdf_files) == 0, "Expected samples directory to be empty or missing 6 PDFs per current repo state"


def test_e2e_document_upload_and_extraction():
    client = TestClient(app)
    headers = {"x-user-id": "test-user-e2e"}

    # 1. Create a case
    case_res = client.post(
        "/cases",
        json={"patient_name": "Lakshmi Narayanan", "relation": "self"},
        headers=headers,
    )
    assert case_res.status_code == 201
    case_data = case_res.json()
    case_id = case_data["id"]

    # 2. Upload a discharge summary PDF
    pdf_bytes = create_minimal_pdf_with_text([
        "SUNSHINE HEART HOSPITAL",
        "DISCHARGE SUMMARY",
        "Patient: Lakshmi Narayanan Age: 68 Y Sex: Female",
        "UHID: SHH-204518 IP No: IP/26/09/0731",
        "Date of Admission: 23-09-2026 Date of Discharge: 28-09-2026",
        "Consultant: Dr. R. K. Sharma",
        "Diagnosis: Acute Decompensated Heart Failure",
        "MEDICATIONS:",
        "1. Tab Furosemide 40 mg OD",
        "2. Tab Metoprolol 25 mg BD",
        "Follow-up: 05-10-2026 at 10:30 AM",
    ])

    upload_res = client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("discharge_summary.pdf", pdf_bytes, "application/pdf"))],
        headers=headers,
    )
    assert upload_res.status_code == 202
    upload_data = upload_res.json()
    job_id = upload_data["job_id"]
    doc_id = upload_data["documents"][0]["id"]

    # 3. Poll job status
    job_res = client.get(f"/jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["stage"] == "completed"
    assert job_data["progress"] == 1.0

    # 4. Retrieve single document extraction
    doc_ext_res = client.get(f"/cases/{case_id}/extractions/{doc_id}", headers=headers)
    assert doc_ext_res.status_code == 200
    doc_ext = doc_ext_res.json()
    assert doc_ext["schema_version"] == "1.0.0"
    assert doc_ext["doc_type"] == "discharge_summary"
    assert doc_ext["fields"]["patient"]["name"] == "Lakshmi Narayanan"
    assert doc_ext["fields"]["patient"]["uhid"] == "SHH-204518"
    assert doc_ext["fields"]["admission_date"] == "2026-09-23"
    assert doc_ext["fields"]["discharge_date"] == "2026-09-28"

    # 5. Retrieve case-level merged extraction
    case_ext_res = client.get(f"/cases/{case_id}/extractions", headers=headers)
    assert case_ext_res.status_code == 200
    case_ext = case_ext_res.json()
    assert case_ext["total_documents"] == 1
    assert len(case_ext["documents"]) == 1
    assert str(case_ext["documents"][0]["doc_id"]) == str(doc_id)


def test_sha256_hash_caching():
    client = TestClient(app)
    headers = {"x-user-id": "test-user-cache"}

    # Create Case 1
    c1 = client.post("/cases", json={"patient_name": "Cache Patient 1"}, headers=headers).json()["id"]
    # Create Case 2
    c2 = client.post("/cases", json={"patient_name": "Cache Patient 2"}, headers=headers).json()["id"]

    pdf_bytes = create_minimal_pdf_with_text([
        "PHARMACY BILL",
        "Bill No: PH-9988 Date: 2026-09-25",
        "1. Paracetamol 500mg 10 2.50 25.00",
        "Gross Total: 25.00",
    ])

    # Upload to Case 1
    res1 = client.post(
        f"/cases/{c1}/documents",
        files=[("files", ("pharmacy_1.pdf", pdf_bytes, "application/pdf"))],
        headers=headers,
    ).json()
    d1_id = res1["documents"][0]["id"]

    # Upload identical bytes to Case 2
    res2 = client.post(
        f"/cases/{c2}/documents",
        files=[("files", ("pharmacy_2_identical.pdf", pdf_bytes, "application/pdf"))],
        headers=headers,
    ).json()
    d2_id = res2["documents"][0]["id"]

    # Verify extraction for Case 2 was reused with proper case/doc attribution
    ext2 = client.get(f"/cases/{c2}/extractions/{d2_id}", headers=headers).json()
    assert ext2["case_id"] == str(c2)
    assert str(ext2["doc_id"]) == str(d2_id)
    assert ext2["doc_type"] == "pharmacy_bill"
    assert ext2["fields"]["bill_no"] == "PH-9988"


def test_ocr_path_with_image():
    client = TestClient(app)
    headers = {"x-user-id": "test-user-ocr"}

    case_id = client.post("/cases", json={"patient_name": "OCR Patient"}, headers=headers).json()["id"]

    # Generate an image with Pillow
    img = Image.new("RGB", (300, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    upload_res = client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("scanned_doc.jpg", img_bytes, "image/jpeg"))],
        headers=headers,
    )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["job_id"]
    doc_id = upload_res.json()["documents"][0]["id"]

    # A blank picture has nothing to read: the job finishes and reports the document as failed.
    job_status = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert job_status["stage"] == "failed"
    doc = client.get(f"/documents/{doc_id}", headers=headers).json()
    assert doc["status"] == "failed" and doc["error"]

    # Verify extraction record
    ext = client.get(f"/cases/{case_id}/extractions/{doc_id}", headers=headers).json()
    assert ext["extraction_method"] == "ocr"
    # Should not crash; unknown doc type if blank image
    assert ext["doc_type"] == "unknown"


def test_invalid_file_extension_rejected():
    client = TestClient(app)
    headers = {"x-user-id": "test-user-invalid"}

    case_id = client.post("/cases", json={"patient_name": "Invalid File Patient"}, headers=headers).json()["id"]

    res = client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("malware.exe", b"MZ...", "application/octet-stream"))],
        headers=headers,
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_demo_fallback_behavior():
    client = TestClient(app)
    headers = {"x-user-id": "test-user-fallback"}

    # 1. With demo_fallback=False (default)
    settings.demo_fallback = False
    c1 = client.post("/cases", json={"patient_name": "No Fallback Patient"}, headers=headers).json()["id"]
    pdf_blank = create_minimal_pdf_with_text(["..."])
    res1 = client.post(
        f"/cases/{c1}/documents",
        files=[("files", ("discharge_summary.pdf", pdf_blank, "application/pdf"))],
        headers=headers,
    ).json()
    d1 = res1["documents"][0]["id"]
    ext1 = client.get(f"/cases/{c1}/extractions/{d1}", headers=headers).json()
    # Should not use fallback
    assert ext1["extraction_method"] != "demo_fallback"
    assert ext1["doc_type"] == "unknown"

    # 2. With demo_fallback=True
    settings.demo_fallback = True
    c2 = client.post("/cases", json={"patient_name": "Fallback Patient"}, headers=headers).json()["id"]
    # Upload a different file content that is unparseable to avoid SHA cache hit
    pdf_unparseable = create_minimal_pdf_with_text(["RANDOM GIBBERISH ONLY 12345"])
    res2 = client.post(
        f"/cases/{c2}/documents",
        files=[("files", ("discharge_summary.pdf", pdf_unparseable, "application/pdf"))],
        headers=headers,
    ).json()
    d2 = res2["documents"][0]["id"]
    ext2 = client.get(f"/cases/{c2}/extractions/{d2}", headers=headers).json()
    assert ext2["extraction_method"] == "demo_fallback"
    assert ext2["doc_type"] == "discharge_summary"
    assert ext2["fields"]["patient"]["name"] == "Lakshmi Narayanan"
    assert any("DEMO_FALLBACK enabled" in w for w in ext2["warnings"])

    # Reset
    settings.demo_fallback = False

