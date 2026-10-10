"""Deterministic parsing for text recognized on the Android device.

OCR is deliberately outside the backend. Android ML Kit supplies page text;
this module classifies and structures that text without an LLM.
"""

import logging
from typing import Any

from ..config import settings
from .classifier import classify_document_text
from .parsers import (
    parse_bill,
    parse_discharge_summary,
    parse_insurance_policy,
    parse_investigation_report,
    parse_unknown,
)
from .schemas import DocumentExtractionEnvelope, utc_now_iso

logger = logging.getLogger("medsure.pipeline")


def parse_recognized_text(
    *,
    case_id: int | str,
    doc_id: int | str,
    recognized_text: str,
    file_hash: str,
    source_filename: str,
    hint_doc_type: str | None = None,
    page_count: int = 1,
    extraction_confidence: float | None = None,
    input_warnings: list[str] | None = None,
) -> DocumentExtractionEnvelope:
    """Classify and parse text already recognized by Android ML Kit."""
    case_str = str(case_id)
    doc_str = str(doc_id)
    warnings = list(input_warnings or [])

    classified_type, class_conf = classify_document_text(recognized_text)
    final_type = classified_type
    if final_type == "unknown" and hint_doc_type and hint_doc_type != "unknown":
        type_mapping = {
            "discharge_summary": "discharge_summary",
            "lab_report": "investigation_report",
            "prescription": "pharmacy_bill",
            "bill": "hospital_bill",
            "policy": "insurance_policy",
            "investigation_report": "investigation_report",
            "hospital_bill": "hospital_bill",
            "pharmacy_bill": "pharmacy_bill",
            "lab_bill": "lab_bill",
            "insurance_policy": "insurance_policy",
        }
        mapped = type_mapping.get(hint_doc_type)
        if mapped:
            final_type = mapped
            class_conf = 0.60
            warnings.append(f"Classification defaulted to device category '{hint_doc_type}'.")

    fields_dict: dict[str, Any]
    if final_type == "discharge_summary":
        parsed_fields, parser_warnings = parse_discharge_summary(recognized_text)
    elif final_type == "investigation_report":
        parsed_fields, parser_warnings = parse_investigation_report(recognized_text)
    elif final_type in ("hospital_bill", "pharmacy_bill", "lab_bill"):
        parsed_fields, parser_warnings = parse_bill(recognized_text, bill_subtype=final_type)
    elif final_type == "insurance_policy":
        parsed_fields, parser_warnings = parse_insurance_policy(recognized_text)
    else:
        final_type = "unknown"
        parsed_fields, parser_warnings = parse_unknown(recognized_text)
    fields_dict = parsed_fields.model_dump()
    warnings.extend(parser_warnings)

    # Synthetic data remains opt-in for demos and never performs OCR.
    if settings.demo_fallback and (final_type == "unknown" or not fields_dict):
        from .demo_fallback import get_demo_fallback_extraction

        fallback = get_demo_fallback_extraction(source_filename)
        if fallback:
            final_type, fields_dict = fallback
            logger.warning("DEMO_FALLBACK used for %s on case %s", source_filename, case_str)
            class_conf = 1.0
            extraction_confidence = 1.0
            warnings.append("DEMO_FALLBACK returned synthetic reference data.")

    return DocumentExtractionEnvelope(
        schema_version="1.0.0",
        doc_id=doc_str,
        case_id=case_str,
        source_file=source_filename,
        file_hash=file_hash,
        doc_type=final_type,
        classification_confidence=class_conf,
        pages=page_count,
        extraction_method="mlkit",
        extraction_confidence=extraction_confidence,
        warnings=warnings,
        extracted_at=utc_now_iso(),
        fields=fields_dict,
    )
