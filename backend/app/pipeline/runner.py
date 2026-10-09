import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from ..config import settings
from .extractor import extract_document_text
from .classifier import classify_document_text
from .parsers import (
    parse_discharge_summary,
    parse_investigation_report,
    parse_bill,
    parse_insurance_policy,
    parse_unknown,
)
from .schemas import DocumentExtractionEnvelope, utc_now_iso
from .storage import (
    save_raw_text,
    save_document_extraction,
    update_case_merged_extraction,
    find_cached_extraction_by_hash,
)

logger = logging.getLogger("medsure.pipeline")


def run_pipeline_for_document(
    case_id: int | str,
    doc_id: int | str,
    file_path: str,
    file_hash: str,
    source_filename: str,
    hint_doc_type: Optional[str] = None,
) -> DocumentExtractionEnvelope:
    """
    Executes the full real extraction pipeline:
    Uploaded document -> Text extraction (OCR when needed) -> Document classification -> Parsing -> Validation -> Structured JSON output.
    Does NOT use any LLM.
    """
    case_str = str(case_id)
    doc_str = str(doc_id)
    warnings = []

    # 1. Check SHA-256 cache
    cached = find_cached_extraction_by_hash(file_hash)
    if cached:
        logger.info(f"Reusing cached extraction for hash {file_hash[:8]} on case {case_str} doc {doc_str}")
        cached_envelope = DocumentExtractionEnvelope(
            schema_version="1.0.0",
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
        save_document_extraction(cached_envelope)
        update_case_merged_extraction(case_str)
        return cached_envelope

    # 2. Text Extraction
    text_result = extract_document_text(file_path)
    warnings.extend(text_result.warnings)

    # Save raw text separately
    save_raw_text(case_str, doc_str, text_result.full_text)

    # 3. Deterministic Classification
    classified_type, class_conf = classify_document_text(text_result.full_text)

    # Map legacy or hint types if classification is indeterminate
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
            warnings.append(f"Classification defaulted to upload category '{hint_doc_type}'.")

    # 4. Parsing based on classified document type
    fields_dict: Dict[str, Any] = {}
    parser_warnings = []

    if final_type == "discharge_summary":
        parsed_fields, p_warns = parse_discharge_summary(text_result.full_text)
        fields_dict = parsed_fields.model_dump()
        parser_warnings.extend(p_warns)

    elif final_type == "investigation_report":
        parsed_fields, p_warns = parse_investigation_report(text_result.full_text)
        fields_dict = parsed_fields.model_dump()
        parser_warnings.extend(p_warns)

    elif final_type in ("hospital_bill", "pharmacy_bill", "lab_bill"):
        parsed_fields, p_warns = parse_bill(text_result.full_text, bill_subtype=final_type)
        fields_dict = parsed_fields.model_dump()
        parser_warnings.extend(p_warns)

    elif final_type == "insurance_policy":
        parsed_fields, p_warns = parse_insurance_policy(text_result.full_text)
        fields_dict = parsed_fields.model_dump()
        parser_warnings.extend(p_warns)

    else:
        final_type = "unknown"
        parsed_fields, p_warns = parse_unknown(text_result.full_text)
        fields_dict = parsed_fields.model_dump()
        parser_warnings.extend(p_warns)

    warnings.extend(parser_warnings)

    # 4b. Optional Demo Fallback for the 6 synthetic samples (OFF by default)
    is_demo_fallback = False
    if settings.demo_fallback and (final_type == "unknown" or not fields_dict):
        from .demo_fallback import get_demo_fallback_extraction
        fb = get_demo_fallback_extraction(source_filename)
        if fb:
            fb_type, fb_fields = fb
            logger.warning(f"DEMO_FALLBACK used for document {source_filename} on case {case_str}")
            final_type = fb_type
            fields_dict = fb_fields
            class_conf = 1.0
            is_demo_fallback = True
            text_result.primary_method = "demo_fallback"
            text_result.confidence = 1.0
            warnings.append("DEMO_FALLBACK enabled: extraction failed or incomplete; returned synthetic sample reference data for demonstration.")

    # 5. Assemble common envelope
    envelope = DocumentExtractionEnvelope(
        schema_version="1.0.0",
        doc_id=doc_str,
        case_id=case_str,
        source_file=source_filename,
        file_hash=file_hash,
        doc_type=final_type,
        classification_confidence=class_conf,
        pages=text_result.page_count,
        extraction_method=text_result.primary_method,
        extraction_confidence=text_result.confidence,
        warnings=warnings,
        extracted_at=utc_now_iso(),
        fields=fields_dict,
    )

    # 6. Save document JSON & update merged case extraction
    save_document_extraction(envelope)
    update_case_merged_extraction(case_str)

    return envelope
