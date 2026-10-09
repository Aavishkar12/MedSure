import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import llm
from app.config import settings
from app.db import get_session
from app.deps import current_user
from app.main import app
from app.models import Case, CaseMember, User

POLICY_TEXT = """[Page 1]
STAR HEALTH FAMILY FLOATER POLICY
Sum Insured: Rs 5,00,000. Co-payment: 10% of every admissible claim.
Room rent is payable up to Rs 4,000 per day.
[Page 2]
Non-payable items: administrative and registration charges, toiletries, attendant food charges."""

POLICY = {
    "insurer": "Star Health",
    "policy_number": "MHA/FF/2026/0048213",
    "sum_insured": 500000.0,
    "room_rent_limit_per_day": 4000.0,
    "copay_percent": 10.0,
    "non_payable_items": ["administrative and registration charges", "toiletries", "attendant food charges"],
}

BILL = [
    {"id": 1, "description": "Room rent - deluxe (5 days @ 5000)", "amount": 25000.0},
    {"id": 2, "description": "2D Echocardiography", "amount": 3200.0},
    {"id": 3, "description": "Administrative & discharge processing", "amount": 3000.0},
    {"id": 4, "description": "Syringe pump charges", "amount": 2400.0},
]

AI_REPLY = {
    "items": [
        {"bill_item_id": 1, "status": "partly_covered", "claimable_amount": 20000,
         "reason": "Room rent is capped at Rs 4,000 a day.", "policy_quote": "Room rent is payable up to Rs 4,000 per day."},
        {"bill_item_id": 2, "status": "covered", "claimable_amount": 3200,
         "reason": "Tests during the stay are covered.", "policy_quote": "this sentence is not in the policy"},
        {"bill_item_id": 3, "status": "not_covered", "claimable_amount": 3000,
         "reason": "Administrative charges are non-payable.", "policy_quote": "administrative and registration charges"},
        # item 4 left out on purpose: it must come back as unclear
    ],
    "notes": ["Submit the claim within 15 days of discharge."],
    "explanation": "Most of the treatment is covered. The room costs more than your policy's daily limit.",
}


def test_report_recomputes_money_and_checks_quotes():
    with patch("app.llm.client._chat", return_value=json.dumps(AI_REPLY)):
        report = llm.compare_bill_to_policy(BILL, POLICY, POLICY_TEXT, "Heart failure")

    items = {i["bill_item_id"]: i for i in report["items"]}
    assert items[1]["status"] == "partly_covered" and items[1]["claimable_amount"] == 20000
    assert items[1]["policy_quote"]  # found in the policy text
    assert items[2]["policy_quote"] == ""  # invented quote removed
    assert items[3]["claimable_amount"] == 0  # not covered counts nothing, whatever the model said
    assert items[4]["status"] == "unclear" and items[4]["claimable_amount"] == 0

    t = report["totals"]
    assert t["billed"] == 33600
    assert t["eligible"] == 23200
    assert t["copay"] == 2320  # 10% co-pay applied in code, not by the model
    assert t["estimated_claimable"] == 20880
    assert t["estimated_out_of_pocket"] == 12720
    assert t["unclear"] == 2400
    assert "Rs 20,880" in report["headline"]
    assert report["method"] == "ai"


def test_claimable_never_exceeds_line_or_sum_insured():
    reply = {"items": [{"bill_item_id": 2, "status": "covered", "claimable_amount": 99999}], "notes": [], "explanation": ""}
    with patch("app.llm.client._chat", return_value=json.dumps(reply)):
        report = llm.compare_bill_to_policy([BILL[1]], {**POLICY, "copay_percent": None, "sum_insured": 1000}, POLICY_TEXT)
    assert report["items"][0]["claimable_amount"] == 3200
    assert report["totals"]["estimated_claimable"] == 1000
    assert "sum insured" in report["notes"][0]


def test_rule_based_report_marks_only_policy_listed_non_payables():
    report = llm.rule_based_report(BILL, POLICY, POLICY_TEXT)
    statuses = {i["bill_item_id"]: i["status"] for i in report["items"]}
    assert statuses == {1: "unclear", 2: "unclear", 3: "not_covered", 4: "unclear"}
    assert report["method"] == "rules"
    assert report["totals"]["estimated_claimable"] == 0


# ---------- API ----------

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    user = User(id="cov_user", phone="9876500000", name="Arjun")
    session.add(user)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(name="case_id")
def case_fixture(session: Session, client):
    case = Case(patient_name="Lakshmi", created_by="cov_user")
    session.add(case)
    session.commit()
    session.add(CaseMember(case_id=case.id, user_id="cov_user", relation="son"))
    session.commit()
    return case.id


def fake_chat(**kwargs):
    """Answers like the model would, depending on which task the system prompt asks for."""
    system = kwargs["messages"][0]["content"]
    if "which charges on a hospital bill" in system:
        bill_lines = json.loads(kwargs["messages"][1]["content"].split("Bill lines:\n")[1])
        ids = [line["bill_item_id"] for line in bill_lines]
        return json.dumps({
            "items": [
                {"bill_item_id": ids[0], "status": "covered", "claimable_amount": 3200, "reason": "Tests are covered.", "policy_quote": ""},
                {"bill_item_id": ids[1], "status": "not_covered", "claimable_amount": 0,
                 "reason": "Administrative charges are non-payable.", "policy_quote": "administrative and registration charges"},
            ],
            "notes": [],
            "explanation": "Your echo test is covered; the admin fee is not.",
        })
    if "insurance policy terms" in kwargs["messages"][1]["content"]:
        return json.dumps(POLICY)
    return json.dumps({"items": [
        {"description": "2D Echocardiography", "amount": 3200},
        {"description": "Administrative & discharge processing", "amount": 3000},
    ]})


def test_bill_and_policy_upload_produce_coverage(client: TestClient, session: Session, case_id: int):
    from app.routers.documents import process_document

    assert client.get(f"/cases/{case_id}/coverage").status_code == 404
    with patch("fastapi.BackgroundTasks.add_task"):
        bill = client.post(
            f"/cases/{case_id}/documents",
            data={"doc_type": "bill", "ocr_text": "FINAL BILL\n2D Echocardiography 3200\nAdministrative & discharge processing 3000"},
            files={"file": ("bill.jpg", b"jpeg-bytes", "image/jpeg")},
        ).json()["documents"][0]["id"]
        pol = client.post(
            f"/cases/{case_id}/documents",
            data={"doc_type": "policy", "ocr_text": POLICY_TEXT},
            files={"file": ("policy.jpg", b"other-jpeg-bytes", "image/jpeg")},
        ).json()["documents"][0]["id"]

    with patch("app.llm.client._chat", side_effect=fake_chat), patch.object(settings, "groq_api_key", "test-key"):
        process_document(bill, session=session)
        # Bill alone: nothing to compare yet.
        assert client.get(f"/cases/{case_id}/coverage").status_code == 404
        process_document(pol, session=session)

    assert client.get(f"/cases/{case_id}/policy").json()["data"]["insurer"] == "Star Health"
    report = client.get(f"/cases/{case_id}/coverage").json()["data"]
    assert [i["status"] for i in report["items"]] == ["covered", "not_covered"]
    assert report["totals"]["estimated_claimable"] == 2880  # 3200 less 10% co-pay
    assert report["items"][1]["policy_quote"] == "administrative and registration charges"
    # The policy must not replace the Discharge Card.
    assert client.get(f"/cases/{case_id}/discharge-card").status_code == 404


def test_run_coverage_needs_bill_and_policy(client: TestClient, case_id: int):
    assert client.post(f"/cases/{case_id}/coverage").status_code == 409
