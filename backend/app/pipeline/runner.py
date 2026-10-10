import logging
from typing import Any, Dict, Optional, Tuple

from ..config import settings
from .classifier import classify_document_text
from .extractor import extract_document_text
from .parsers import (
    parse_bill,
    parse_discharge_summary,
    parse_insurance_policy,
    parse_investigation_report,
    parse_unknown,
)
from .schemas import DocumentExtractionEnvelope, utc_now_iso

logger = logging.getLogger("medsure.pipeline")

# Upload categories the app sends -> the parser to try when the text alone does not say what it is.
# A prescription has no parser of its own; it is read by the LLM only.
HINT_TO_PIPELINE_TYPE = {
    "discharge_summary": "discharge_summary",
    "lab_report": "investigation_report",
    "investigation_report": "investigation_report",
    "bill": "hospital_bill",
    "hospital_bill": "hospital_bill",
    "pharmacy_bill": "pharmacy_bill",
    "lab_bill": "lab_bill",
    "policy": "insurance_policy",
    "insurance_policy": "insurance_policy",
}


def run_pipeline_for_document(
    case_id: int | str,
    doc_id: int | str,
    file_path: str,
    file_hash: str,
    source_filename: str,
    hint_doc_type: Optional[str] = None,
    supplied_text: Optional[str] = None,
    cached: Optional[Dict[str, Any]] = None,
) -> Tuple[DocumentExtractionEnvelope, str]:
    """
    Uploaded document -> text (PDF text layer, or text read on the phone) -> classification -> rule-based parsing.
    Returns structured JSON with the full page-marked text. Persistence belongs
    to the API layer so database transactions remain the source of truth.
    """
    case_str = str(case_id)
    doc_str = str(doc_id)
    warnings = []

    # 1. Same file seen before: reuse its text and parse.
    if cached:
        logger.info(f"Reusing cached extraction for hash {file_hash[:8]} on case {case_str} doc {doc_str}")
        envelope = DocumentExtractionEnvelope(
            doc_id=doc_str,
            case_id=case_str,
            source_file=source_filename,
            file_hash=file_hash,
            doc_type=cached.get("doc_type", "unknown"),
            classification_confidence=cached.get("classification_confidence"),
            pages=cached.get("pages", 1),
            extraction_method=cached.get("extraction_method", "text_layer"),
            extraction_confidence=cached.get("extraction_confidence"),
            warnings=cached.get("warnings", []) + ["Extraction reused from file-hash cache."],
            extracted_at=utc_now_iso(),
            fields=cached.get("fields", {}),
        )
        text = cached.get("raw_text", "")
        return envelope, text

    # 2. Text extraction
    text_result = extract_document_text(file_path, supplied_text)
    warnings.extend(text_result.warnings)

    # 3. Deterministic classification, falling back to the category the user uploaded it under
    final_type, class_conf = classify_document_text(text_result.full_text)
    if final_type == "unknown" and hint_doc_type in HINT_TO_PIPELINE_TYPE and text_result.full_text:
        final_type = HINT_TO_PIPELINE_TYPE[hint_doc_type]
        class_conf = 0.60
        warnings.append(f"Classification defaulted to upload category '{hint_doc_type}'.")

    # 4. Rule-based parsing for the classified type
    text = text_result.full_text
    if final_type == "discharge_summary":
        parsed, p_warns = parse_discharge_summary(text)
    elif final_type == "investigation_report":
        parsed, p_warns = parse_investigation_report(text)
    elif final_type in ("hospital_bill", "pharmacy_bill", "lab_bill"):
        parsed, p_warns = parse_bill(text, bill_subtype=final_type)
    elif final_type == "insurance_policy":
        parsed, p_warns = parse_insurance_policy(text)
    else:
        final_type = "unknown"
        parsed, p_warns = parse_unknown(text)
    fields_dict: Dict[str, Any] = parsed.model_dump()
    warnings.extend(p_warns)

    # 4b. Optional demo fallback for the six synthetic samples (OFF by default). Never cached.
    method, confidence = text_result.primary_method, text_result.confidence
    if settings.demo_fallback and final_type == "unknown":
        from .demo_fallback import get_demo_fallback_extraction

        fb = get_demo_fallback_extraction(source_filename)
        if fb:
            logger.warning(f"DEMO_FALLBACK used for document {source_filename} on case {case_str}")
            final_type, fields_dict = fb
            class_conf, method, confidence = 1.0, "demo_fallback", 1.0
            warnings.append(
                "DEMO_FALLBACK enabled: extraction failed or incomplete; returned synthetic sample reference data for demonstration."
            )

    envelope = DocumentExtractionEnvelope(
        doc_id=doc_str,
        case_id=case_str,
        source_file=source_filename,
        file_hash=file_hash,
        doc_type=final_type,
        classification_confidence=class_conf,
        pages=text_result.page_count,
        extraction_method=method,
        extraction_confidence=confidence,
        warnings=warnings,
        extracted_at=utc_now_iso(),
        fields=fields_dict,
    )
    return envelope, text
