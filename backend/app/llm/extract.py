"""Document text -> validated structured data. One call per document type."""

import json
import logging
import re
from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, ValidationError

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
    summary: str = ""  # what happened during this stay, in plain words
    hospital: Optional[str] = None
    doctor: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    diagnosis: Diagnosis
    other_diagnoses: list[Diagnosis] = []
    medicines: list[Medicine] = []
    lab_values: list[LabValue] = []
    precautions: list[Precaution] = []
    warning_signs: list[Precaution] = []  # when the document says to get help
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
class SubLimit(BaseModel):
    item: str  # e.g. "Cataract surgery", "ICU per day"
    limit: str  # as written, e.g. "Rs 40,000 per eye" or "2% of sum insured"
    limit_amount: Optional[float] = None  # rupees, only when the policy states a fixed amount
    source_page: Optional[int] = None


class PolicyData(BaseModel):
    policy_number: Optional[str] = None
    insurer: Optional[str] = None
    policyholder_name: Optional[str] = None
    insured_members: list[str] = []
    policy_start: Optional[str] = None
    policy_end: Optional[str] = None
    sum_insured: Optional[float] = None  # rupees
    room_rent_limit: Optional[str] = None  # as written
    room_rent_limit_per_day: Optional[float] = None  # rupees, only when a fixed amount is stated
    copay_percent: Optional[float] = None  # e.g. 10 for "10% co-payment"
    deductible: Optional[float] = None
    pre_hospitalisation_days: Optional[int] = None
    post_hospitalisation_days: Optional[int] = None
    sub_limits: list[SubLimit] = []
    exclusions: list[str] = []
    non_payable_items: list[str] = []  # consumables / items the policy lists as not payable
    waiting_periods: list[str] = []
    preauth_requirement: Optional[str] = None
    claim_submission_deadline: Optional[str] = None
    plain_summary: str = ""  # what this policy pays for, in two or three plain sentences
    source_page: Optional[int] = None


RULES = f"""You explain a patient's own hospital documents to their family in plain, calm language.
Rules:
- Use ONLY what is written in the document. If something is not there, leave it empty. Never guess,
  and never fill in a typical value: a medicine, dose, test result or date that is not in this
  document must not appear in your reply.
- Copy names of medicines, tests and diagnoses exactly as the document spells them.
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

CARD_TASK = """Extract a Discharge Card from this discharge summary / medical record.
- summary: two to four plain sentences on why the patient was admitted, what was done and how they
  were at discharge, using only what the document says.
- diagnosis: the main (final / discharge) diagnosis. Put any other diagnoses in other_diagnoses.
- medicines: every medicine in the discharge / home medication list with its dose, how often and for
  how long, exactly as written. Do not include medicines that were only given in hospital and stopped.
  Write the schedule in plain words ("twice a day, morning and night" for BD / 1-0-1).
- precautions: diet, activity and care advice from the document.
- warning_signs: the symptoms the document says need urgent attention or a call to the doctor.
- follow_ups: each review visit or test the document asks for, with when it is due."""
BILL_TASK = """Extract every billed line item from this hospital bill. Skip subtotals, totals, taxes and payments.
Extract unit prices, quantities, and line amounts where visible.
Set worth_asking to true only for things visible in the bill itself: duplicated lines, unusually
high quantities, or vague descriptions like "miscellaneous". Give the reason in ask_reason, phrased
as a neutral question for the billing desk, never as an accusation.
Set total_billed to the bill's printed grand total if there is one."""
PRESCRIPTION_TASK = """Extract all prescribed medications from this medical prescription.
Preserve exact medicine names, dosage frequencies, forms, and instructions as written.
If handwriting is ambiguous or instructions appear contradictory, set flag_for_confirmation to true
with an explanation in flag_reason."""
LAB_TASK = """Extract all laboratory test results from this diagnostic report.
Preserve exact reported values, units, and reference ranges.
Categorize flag as low, normal, high, abnormal, or unknown based ONLY on the report's reference range.
Provide a calm, plain explanation of what each test measures."""
POLICY_TASK = """Extract the health insurance policy terms that decide what a hospital bill claim pays.
- Amounts are in rupees as plain numbers (500000, not "5 lakh"). Leave a number null unless the policy
  states a fixed amount; keep the wording in the matching text field (e.g. room_rent_limit "1% of sum insured per day").
- copay_percent: the co-payment percentage that applies to this insured person, if any.
- sub_limits: every cap on a specific treatment, room type, ICU, ambulance, etc.
- exclusions, non_payable_items, waiting_periods: list each one as written, briefly.
- plain_summary: two or three plain sentences on what this policy pays for and its main limits.
Distinguish explicit policy text from any interpretation. Never guarantee claim approval."""

T = TypeVar("T", bound=BaseModel)


def _extract(schema: type[T], task: str, text: str, images: list[bytes]) -> T:
    system = RULES + json.dumps(schema.model_json_schema())
    if text and images:
        body = f"OCR text of the attached pages (may contain reading errors; trust the images):\n{text[:MAX_TEXT_CHARS]}"
    elif text:
        body = f"Document text:\n{text[:MAX_TEXT_CHARS]}"
    else:
        body = "The document pages are attached as images."
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


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


# Dosage-form words that come before a medicine's name and say nothing about which medicine it is.
_FORM_WORDS = {"tab", "tabs", "tablet", "cap", "caps", "capsule", "inj", "injection", "syp", "syrup", "susp", "oint", "gel", "drops", "t", "c"}


def in_document(name: str, doc_text: str) -> bool:
    """True when the distinctive word of a name (medicine, test) appears in the document text."""
    words = [w for w in _norm(name).split() if w not in _FORM_WORDS and not w.isdigit()]
    key = max(words, key=len, default="")
    if len(key) < 3:
        return True  # too short to check reliably
    return f" {key[:6]}" in f" {_norm(doc_text)}"  # first 6 letters: tolerates plural / brand suffixes


def extract_discharge_card(text: str, images: list[bytes] | None = None) -> dict:
    card = _extract(DischargeCardData, CARD_TASK, text, images or [])
    for lab in card.lab_values:
        lab.concept = _clean_concept(lab.concept)
    if text and not images:
        # Grounding check: a medicine or test the model names must be in this document.
        # Lab names are often abbreviated in reports ("Hb"), so a lab value may match on its number instead.
        def lab_found(lab: LabValue) -> bool:
            return in_document(lab.name, text) or (lab.value.strip() != "" and lab.value.strip() in text)

        dropped = [m.name for m in card.medicines if not in_document(m.name, text)]
        dropped += [lab.name for lab in card.lab_values if not lab_found(lab)]
        if dropped:
            logger.warning(f"Dropped items not found in the document: {dropped}")
        card.medicines = [m for m in card.medicines if in_document(m.name, text)]
        card.lab_values = [lab for lab in card.lab_values if lab_found(lab)]
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
    if text and not images:
        rx.medicines = [m for m in rx.medicines if in_document(m.medicine_name, text)]
    return {**rx.model_dump(), "disclaimer": DISCLAIMER}


def extract_lab_report(text: str, images: list[bytes] | None = None) -> dict:
    lab = _extract(LabReportData, LAB_TASK, text, images or [])
    for res in lab.results:
        res.concept = _clean_concept(res.concept)
    return {**lab.model_dump(), "disclaimer": DISCLAIMER}


def extract_policy(text: str, images: list[bytes] | None = None) -> dict:
    pol = _extract(PolicyData, POLICY_TASK, text, images or [])
    return {**pol.model_dump(), "disclaimer": DISCLAIMER}
