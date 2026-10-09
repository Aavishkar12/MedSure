"""Document text -> validated structured data. One call per document type."""

import json
import logging
from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, Field, ValidationError

from .client import complete_json

logger = logging.getLogger("medsure.extract")

MAX_TEXT_CHARS = 24_000
DISCLAIMER = "This explains your documents. It is not medical advice."

# Fixed vocabulary so report values, bill items and check-in questions link exactly.
CONCEPTS = [
    "kidney_function", "liver_function", "blood_sugar", "blood_pressure", "heart", "infection",
    "blood_count", "breathing", "pain", "wound_care", "nutrition", "imaging", "surgery",
    "medicines", "room_and_nursing",
]


class Diagnosis(BaseModel):
    name: str
    plain: str
    source_page: Optional[int] = None


class Medicine(BaseModel):
    name: str
    dose: str = ""
    schedule: str = ""
    days: Optional[int] = None
    purpose: str = ""
    source_page: Optional[int] = None


class LabValue(BaseModel):
    name: str
    value: str
    unit: str = ""
    range: str = ""
    status: Literal["low", "normal", "high", "unknown"] = "unknown"
    plain: str = ""
    concept: Optional[str] = None
    source_page: Optional[int] = None


class Precaution(BaseModel):
    text: str
    source_page: Optional[int] = None


class FollowUp(BaseModel):
    what: str
    when: str = ""
    source_page: Optional[int] = None


class DischargeCardData(BaseModel):
    diagnosis: Diagnosis
    medicines: list[Medicine] = []
    lab_values: list[LabValue] = []
    precautions: list[Precaution] = []
    follow_ups: list[FollowUp] = []


class BillLine(BaseModel):
    description: str
    amount: float
    quantity: Optional[float] = 1.0
    unit_price: Optional[float] = None
    explanation: str = ""
    worth_asking: bool = False
    ask_reason: Optional[str] = None
    concept: Optional[str] = None


class BillData(BaseModel):
    items: list[BillLine]
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    hospital_name: Optional[str] = None
    total_billed: Optional[float] = None
    patient_payable: Optional[float] = None
    discrepancy_note: Optional[str] = None


# --- Prescription Extraction Model ---
class PrescriptionItem(BaseModel):
    medicine_name: str
    strength: Optional[str] = ""
    form: Optional[str] = ""  # tablet, syrup, capsule, injection, ointment
    dosage_frequency: str = ""  # e.g., 1-0-1 after food
    duration: Optional[str] = ""
    instructions: Optional[str] = ""  # before/after meals, with water, precautions
    flag_for_confirmation: bool = False
    flag_reason: Optional[str] = None
    source_page: Optional[int] = None


class PrescriptionData(BaseModel):
    doctor_name: Optional[str] = None
    date: Optional[str] = None
    medicines: list[PrescriptionItem] = []
    general_advice: list[str] = []


# --- Lab Report Extraction Model ---
class LabReportItem(BaseModel):
    test_name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    flag: Literal["low", "normal", "high", "abnormal", "unknown"] = "unknown"
    plain_explanation: str = ""
    concept: Optional[str] = None
    source_page: Optional[int] = None


class LabReportData(BaseModel):
    patient_name: Optional[str] = None
    collection_date: Optional[str] = None
    lab_name: Optional[str] = None
    results: list[LabReportItem] = []
    summary: str = ""


# --- Insurance Policy Extraction Model ---
class PolicyData(BaseModel):
    policy_number: Optional[str] = None
    insurer: Optional[str] = None
    policyholder_name: Optional[str] = None
    sum_insured: Optional[str] = None
    room_rent_limit: Optional[str] = None
    copay: Optional[str] = None
    exclusions: list[str] = []
    preauth_requirement: Optional[str] = None
    claim_submission_deadline: Optional[str] = None
    source_page: Optional[int] = None


RULES = f"""You explain a patient's own hospital documents to their family in plain, calm language.
Rules:
- Use ONLY what is written in the document. If something is not there, leave it empty. Never guess.
- Do not diagnose, predict outcomes, or recommend treatment. Explain what the document already says.
- Write explanations for someone with no medical background, one or two short sentences each.
  Use everyday words ("protects the stomach from acid", not "acid suppression") and say what a
  medical term means the first time you use it. Never sound alarming or judgemental.
- For a medicine's purpose, say what that kind of medicine is generally used for.
- For a lab value, say what the test measures and whether the document shows it as low, normal or high.
  If a value was measured more than once, use the latest and mention the earlier one in "plain".
- Never alter doctor prescriptions or suggest alternative medicines.
- source_page is the number from the nearest [Page N] marker, or null if unknown.
- concept must be one of {CONCEPTS} or null.
Reply with a single JSON object matching this JSON Schema:
"""

CARD_TASK = "Extract a Discharge Card from this discharge summary / medical record."
BILL_TASK = """Extract every billed line item from this hospital bill.
Extract unit prices, quantities, and line amounts where visible.
Set worth_asking to true only for things visible in the bill itself: duplicated lines, unusually
high quantities, or vague descriptions like "miscellaneous". Give the reason in ask_reason, phrased
as a neutral question for the billing desk, never as an accusation.
Calculate total_billed if present on the document."""
PRESCRIPTION_TASK = """Extract all prescribed medications from this medical prescription.
Preserve exact medicine names, dosage frequencies, forms, and instructions as written.
If handwriting is ambiguous or instructions appear contradictory, set flag_for_confirmation to true
with an explanation in flag_reason."""
LAB_TASK = """Extract all laboratory test results from this diagnostic report.
Preserve exact reported values, units, and reference ranges.
Categorize flag as low, normal, high, abnormal, or unknown based ONLY on the report's reference range.
Provide a calm, plain explanation of what each test measures."""
POLICY_TASK = """Extract key health insurance policy clauses from this policy document.
Extract sum insured, room rent limits, copay clauses, pre-authorization deadlines, and claim requirements.
Distinguish explicit policy text from any interpretation. Never guarantee claim approval."""

T = TypeVar("T", bound=BaseModel)


def _extract(schema: type[T], task: str, text: str, images: list[bytes]) -> T:
    system = RULES + json.dumps(schema.model_json_schema())
    body = f"Document text:\n{text[:MAX_TEXT_CHARS]}" if text else "The document pages are attached as images."
    user = f"{task}\n\n{body}"
    error = ""
    for _ in range(2):  # one retry with the validation error fed back
        try:
            return schema.model_validate(complete_json(system, user + error, images or None))
        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Validation error during extraction: {e}")
            error = f"\n\nYour previous reply was invalid: {str(e)[:1500]}\nReturn corrected JSON only."
    raise ValueError("Model did not return valid data for this document")


def _clean_concept(value: Optional[str]) -> Optional[str]:
    return value if value in CONCEPTS else None


def extract_discharge_card(text: str, images: list[bytes] | None = None) -> dict:
    card = _extract(DischargeCardData, CARD_TASK, text, images or [])
    for lab in card.lab_values:
        lab.concept = _clean_concept(lab.concept)
    return {**card.model_dump(), "disclaimer": DISCLAIMER}


def extract_bill(text: str, images: list[bytes] | None = None) -> list[dict]:
    bill = _extract(BillData, BILL_TASK, text, images or [])
    for item in bill.items:
        item.concept = _clean_concept(item.concept)

    # Validate arithmetic discrepancies deterministically
    calc_sum = sum(item.amount for item in bill.items)
    discrepancy = None
    if bill.total_billed is not None and abs(calc_sum - bill.total_billed) > 1.0:
        discrepancy = f"Line items sum to {calc_sum:.2f}, while document total is {bill.total_billed:.2f}."

    items_dump = [item.model_dump() for item in bill.items]
    if discrepancy and items_dump:
        items_dump[0]["ask_reason"] = (
            f"Note: {discrepancy} " + (items_dump[0].get("ask_reason") or "")
        ).strip()
    return items_dump


def extract_prescription(text: str, images: list[bytes] | None = None) -> dict:
    rx = _extract(PrescriptionData, PRESCRIPTION_TASK, text, images or [])
    return {**rx.model_dump(), "disclaimer": DISCLAIMER}


def extract_lab_report(text: str, images: list[bytes] | None = None) -> dict:
    lab = _extract(LabReportData, LAB_TASK, text, images or [])
    for res in lab.results:
        res.concept = _clean_concept(res.concept)
    return {**lab.model_dump(), "disclaimer": DISCLAIMER}


def extract_policy(text: str, images: list[bytes] | None = None) -> dict:
    pol = _extract(PolicyData, POLICY_TASK, text, images or [])
    return {**pol.model_dump(), "disclaimer": DISCLAIMER}
