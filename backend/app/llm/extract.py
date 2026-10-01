"""Document text -> validated structured data. One call per document type."""

import json
from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from .client import complete_json

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
    explanation: str = ""
    worth_asking: bool = False
    ask_reason: Optional[str] = None
    concept: Optional[str] = None


class BillData(BaseModel):
    items: list[BillLine]


RULES = f"""You explain a patient's own hospital documents to their family in plain, calm language.
Rules:
- Use ONLY what is written in the document. If something is not there, leave it empty. Never guess.
- Do not diagnose, predict outcomes, or recommend treatment. Explain what the document already says.
- Write explanations for someone with no medical background, one or two short sentences each.
- source_page is the number from the nearest [Page N] marker, or null if unknown.
- concept must be one of {CONCEPTS} or null.
Reply with a single JSON object matching this JSON Schema:
"""

CARD_TASK = "Extract a Discharge Card from this discharge summary / report."
BILL_TASK = """Extract every billed line item from this hospital bill. Skip subtotals, totals and taxes.
Set worth_asking to true only for things visible in the bill itself: duplicated lines, unusually
high quantities, or vague descriptions like "miscellaneous". Give the reason in ask_reason, phrased
as a neutral question for the billing desk, never as an accusation."""

T = TypeVar("T", bound=BaseModel)


def _extract(schema: type[T], task: str, text: str, images: list[bytes]) -> T:
    system = RULES + json.dumps(schema.model_json_schema())
    body = f"Document text:\n{text[:MAX_TEXT_CHARS]}" if text else "The document pages are attached as images."
    user = f"{task}\n\n{body}"
    error = ""
    for _ in range(2):  # one retry with the validation error fed back
        try:
            return schema.model_validate(complete_json(system, user + error, images or None))
        except (ValidationError, json.JSONDecodeError) as e:
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
    return [item.model_dump() for item in bill.items]
