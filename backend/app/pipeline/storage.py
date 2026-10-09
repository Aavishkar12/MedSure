import json
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..config import settings
from .schemas import DocumentExtractionEnvelope, CaseExtractionEnvelope


def _atomic_write_file(target_path: Path, content: str) -> None:
    """Writes content to a temporary file in the same directory and atomically renames it."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(dir=str(target_path.parent), prefix="tmp_ms_")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        # On Windows, os.replace replaces existing file atomically
        os.replace(temp_name, str(target_path))
    except Exception:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        raise


def get_extractions_base_dir() -> Path:
    base = Path(settings.extractions_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_case_dir(case_id: str | int) -> Path:
    case_path = get_extractions_base_dir() / str(case_id)
    case_path.mkdir(parents=True, exist_ok=True)
    return case_path


def save_raw_text(case_id: str | int, doc_id: str | int, raw_text: str) -> str:
    """Stores per-page raw extracted text separately in data/extractions/{case_id}/{doc_id}_raw.txt"""
    target = get_case_dir(case_id) / f"{doc_id}_raw.txt"
    _atomic_write_file(target, raw_text)
    return str(target)


def save_document_extraction(extraction: DocumentExtractionEnvelope) -> str:
    """Saves document extraction JSON: data/extractions/{case_id}/{doc_id}.json"""
    target = get_case_dir(extraction.case_id) / f"{extraction.doc_id}.json"
    json_str = extraction.model_dump_json(indent=2)
    _atomic_write_file(target, json_str)
    return str(target)


def load_document_extraction(case_id: str | int, doc_id: str | int) -> Optional[DocumentExtractionEnvelope]:
    """Loads document extraction JSON from disk if present."""
    target = get_case_dir(case_id) / f"{doc_id}.json"
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return DocumentExtractionEnvelope(**data)
    except Exception:
        return None


def update_case_merged_extraction(case_id: str | int) -> CaseExtractionEnvelope:
    """
    Scans data/extractions/{case_id}/ for all doc JSONs and writes
    the merged data/extractions/{case_id}/case_extraction.json.
    """
    case_dir = get_case_dir(case_id)
    docs: List[DocumentExtractionEnvelope] = []

    for item in case_dir.glob("*.json"):
        if item.name == "case_extraction.json":
            continue
        try:
            content = json.loads(item.read_text(encoding="utf-8"))
            if "schema_version" in content and "doc_id" in content:
                docs.append(DocumentExtractionEnvelope(**content))
        except Exception:
            continue

    # Sort stably by doc_id
    docs.sort(key=lambda d: str(d.doc_id))

    case_envelope = CaseExtractionEnvelope(
        schema_version="1.0.0",
        case_id=str(case_id),
        total_documents=len(docs),
        documents=docs,
    )

    merged_target = case_dir / "case_extraction.json"
    _atomic_write_file(merged_target, case_envelope.model_dump_json(indent=2))
    return case_envelope


def find_cached_extraction_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    """
    Searches extractions across all cases for an extraction matching file_hash.
    Returns the extraction dictionary if found, or None.
    """
    base_dir = get_extractions_base_dir()
    for case_folder in base_dir.iterdir():
        if not case_folder.is_dir():
            continue
        for json_file in case_folder.glob("*.json"):
            if json_file.name == "case_extraction.json":
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("file_hash") == file_hash and not data.get("is_demo_fallback"):
                    return data
            except Exception:
                continue
    return None
