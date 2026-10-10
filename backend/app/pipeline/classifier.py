import re
from typing import Tuple, Dict, List


CLASSIFICATION_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "discharge_summary": {
        "titles": [
            "discharge summary",
            "discharge card",
            "discharge note",
            "summary of discharge",
            "inpatient discharge",
        ],
        "strong": [
            "admission date",
            "discharge date",
            "date of admission",
            "date of discharge",
            "condition at discharge",
            "discharge diagnosis",
            "diagnosis at discharge",
            "uhid",
            "ip number",
            "ip no",
            "discharge advice",
            "discharge medications",
        ],
        "context": [
            "consultant",
            "treating doctor",
            "follow up",
            "blood group",
            "warning signs",
            "emergency signs",
            "diet advice",
        ],
    },
    "investigation_report": {
        "titles": [
            "investigation report",
            "diagnostic report",
            "laboratory report",
            "lab report",
            "pathology report",
            "radiology report",
            "clinical lab report",
        ],
        "strong": [
            "reference range",
            "reference interval",
            "normal range",
            "observed value",
            "test result",
            "imaging findings",
            "echocardiogram",
            "ecg report",
            "lvef",
            "x-ray chest",
            "impression:",
        ],
        "context": [
            "biochemistry",
            "hematology",
            "specimen",
            "sample collected",
            "reported on",
            "units",
            "findings",
        ],
    },
    "pharmacy_bill": {
        "titles": [
            "pharmacy bill",
            "pharmacy cash memo",
            "pharmacy invoice",
            "chemist invoice",
            "retail drug invoice",
            "medical store",
        ],
        "strong": [
            "pharmacy",
            "chemist & druggist",
            "drug licence",
            "dl no",
            "batch no",
            "expiry date",
            "exp date",
            "mrp",
        ],
        "context": [
            "dispensed by",
            "pharmacist",
            "rx",
            "schedule h",
            "gstin",
            "strip",
            "tab",
            "cap",
        ],
    },
    "lab_bill": {
        "titles": [
            "lab invoice",
            "lab bill",
            "laboratory invoice",
            "diagnostic centre invoice",
            "investigation bill",
            "pathology bill",
        ],
        "strong": [
            "lab invoice",
            "laboratory invoice",
            "diagnostic invoice",
            "investigation charges",
            "test charges",
        ],
        "context": [
            "diagnostic center",
            "diagnostics",
            "sample id",
            "collection charges",
        ],
    },
    "hospital_bill": {
        "titles": [
            "hospital bill",
            "inpatient bill",
            "final bill",
            "ip bill",
            "hospital final bill",
            "indoor patient bill",
            "discharge bill",
            "interim bill",
        ],
        "strong": [
            "gross total",
            "advance paid",
            "balance due",
            "net payable",
            "room charges",
            "nursing charges",
            "ot charges",
            "icu charges",
            "bed charges",
        ],
        "context": [
            "bill no",
            "invoice no",
            "line items",
            "bill date",
            "payment receipt",
            "settlement",
        ],
    },
    "insurance_policy": {
        "titles": [
            "insurance policy",
            "policy schedule",
            "certificate of insurance",
            "health insurance policy",
            "family floater policy",
            "mediclaim policy",
        ],
        "strong": [
            "sum insured",
            "policyholder",
            "policy period",
            "co-pay",
            "copay",
            "room rent limit",
            "pre-hospitalisation",
            "post-hospitalisation",
            "third party administrator",
            "tpa name",
            "claim submission",
            "non-payable",
        ],
        "context": [
            "insurer",
            "insurance company",
            "insured members",
            "inception date",
            "uhid / card no",
            "cashless network",
        ],
    },
}


def classify_document_text(text: str) -> Tuple[str, float]:
    """
    Deterministically classifies document text without any LLM.
    Returns (doc_type, confidence).
    doc_type is one of:
      - 'discharge_summary'
      - 'investigation_report'
      - 'hospital_bill'
      - 'pharmacy_bill'
      - 'lab_bill'
      - 'insurance_policy'
      - 'unknown'
    """
    if not text or len(text.strip()) < 20:
        return "unknown", 0.0

    lower_text = text.lower()

    # Pre-check for title near the top of the document (first 600 characters)
    header_chunk = lower_text[:700]

    scores: Dict[str, float] = {
        "discharge_summary": 0.0,
        "investigation_report": 0.0,
        "hospital_bill": 0.0,
        "pharmacy_bill": 0.0,
        "lab_bill": 0.0,
        "insurance_policy": 0.0,
    }

    for doc_type, criteria in CLASSIFICATION_KEYWORDS.items():
        # Title matches in header chunk carry heavy weight
        for title in criteria["titles"]:
            if title in header_chunk:
                scores[doc_type] += 40.0
            elif title in lower_text:
                scores[doc_type] += 20.0

        # Strong keyword matches
        for kw in criteria["strong"]:
            matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", lower_text))
            if matches > 0:
                scores[doc_type] += min(matches * 8.0, 32.0)

        # Contextual matches
        for kw in criteria["context"]:
            matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", lower_text))
            if matches > 0:
                scores[doc_type] += min(matches * 3.0, 15.0)

    # Disambiguation rules between bills
    # If pharmacy indicators are strong, pharmacy_bill should take precedence over hospital_bill
    if "pharmacy" in header_chunk or "chemist" in header_chunk or "batch no" in lower_text:
        scores["pharmacy_bill"] += 25.0

    # If lab invoice / lab bill title is present, lab_bill takes precedence
    if "lab invoice" in header_chunk or "lab bill" in header_chunk or "diagnostic invoice" in header_chunk:
        scores["lab_bill"] += 30.0

    # Sort candidates by score
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_type, best_score = sorted_scores[0]

    # Threshold for classification
    # If score is too low or not enough distinction, mark as unknown
    if best_score < 25.0:
        return "unknown", 0.0

    # Compute a normalized confidence score between 0.65 and 0.99
    confidence = min(0.65 + (best_score / 150.0) * 0.34, 0.99)
    return best_type, round(confidence, 2)
