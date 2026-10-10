"""Uploaded file -> text with [Page N] markers.

The server never looks at page images. Text comes from one of two places:
  - the PDF's own text layer (typed documents), or
  - text the phone read on the device with ML Kit and sent along with the upload.
A scan or photo that arrives without phone text cannot be read, and says so.
"""

from pathlib import Path
from typing import List, Optional

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp")
TEXT_EXTENSIONS = (".txt",)
NEEDS_PHONE_TEXT = (
    "This is a scan or photo with no readable text. Add it with \"Scan with camera\" in the app, "
    "or upload it from the phone again so the text can be read on the device."
)


class PageExtraction:
    def __init__(self, page_num: int, text: str, method: str = "text_layer", confidence: float = 1.0, is_blank: bool = False):
        self.page_num = page_num
        self.text = text
        self.method = method
        self.confidence = confidence
        self.is_blank = is_blank


class DocumentTextResult:
    def __init__(
        self,
        pages: List[PageExtraction],
        page_count: int,
        primary_method: str,
        confidence: float,
        warnings: List[str],
        full_text: str,
    ):
        self.pages = pages
        self.page_count = page_count
        self.primary_method = primary_method
        self.confidence = confidence
        self.warnings = warnings
        self.full_text = full_text


def _is_usable_text(text: str) -> bool:
    """A page has usable text if it has at least 30 non-whitespace characters."""
    return len("".join(text.split())) >= 30


def _result(pages: List[PageExtraction], page_count: int, warnings: List[str]) -> DocumentTextResult:
    confidence = round(sum(p.confidence for p in pages) / len(pages), 2) if pages else 0.0
    full_text = "\n\n".join(f"[Page {p.page_num}]\n{p.text}" for p in pages if p.text)
    return DocumentTextResult(pages, page_count, "text_layer", confidence, warnings, full_text)


def _from_phone(supplied_text: str, page_count: int = 0) -> DocumentTextResult:
    """Text read on the phone. It already carries [Page N] markers when there are several pages."""
    text = supplied_text.strip()
    if "[Page " not in text:
        text = f"[Page 1]\n{text}"
    pages = max(text.count("[Page "), page_count, 1)
    return DocumentTextResult([PageExtraction(1, text, "device_ocr", 0.9)], pages, "device_ocr", 0.9, [], text)


def _unreadable(page_count: int, warnings: List[str]) -> DocumentTextResult:
    return DocumentTextResult([], page_count, "unknown", 0.0, warnings + [NEEDS_PHONE_TEXT], "")


def extract_document_text(file_path: str, supplied_text: Optional[str] = None) -> DocumentTextResult:
    """
    Text page by page. A typed PDF is read from its own text layer, which is exact. Anything else
    (scanned PDF, photo) uses supplied_text: what the phone read on the device.
    """
    phone_text = supplied_text if supplied_text and _is_usable_text(supplied_text) else None
    path = Path(file_path) if file_path else None

    if not path or not path.exists():
        if phone_text:
            return _from_phone(phone_text)
        return DocumentTextResult([], 0, "unknown", 0.0, ["File not found"], "")

    ext = path.suffix.lower()

    if ext in TEXT_EXTENSIONS:
        if phone_text:  # text sent on its own is stored as a .txt file
            return _from_phone(phone_text)
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return _result([PageExtraction(1, text, "text_layer", 1.0, not text)], 1, [])

    if ext in IMAGE_EXTENSIONS:
        return _from_phone(phone_text, 1) if phone_text else _unreadable(1, [])

    if ext == ".pdf":
        try:
            import pymupdf

            with pymupdf.open(path) as pdf:
                page_count = pdf.page_count
                layers = [page.get_text().strip() for page in pdf]
        except Exception as e:
            if phone_text:
                return _from_phone(phone_text)
            return DocumentTextResult([], 0, "text_layer", 0.0, [f"Failed to read PDF: {e}"], "")

        if page_count == 0:
            return DocumentTextResult([], 0, "text_layer", 0.0, ["PDF contains 0 pages"], "")
        typed = [_is_usable_text(layer) for layer in layers]
        if all(typed):
            return _result([PageExtraction(i, layer, "text_layer", 0.98) for i, layer in enumerate(layers, 1)], page_count, [])
        if phone_text:  # a scan, or a mix of typed and scanned pages: the phone read every page
            return _from_phone(phone_text, page_count)
        if not any(typed):
            return _unreadable(page_count, [])
        # Some pages are typed and some are pictures, and the phone sent no text: keep what can be read.
        pages, warnings = [], []
        for i, layer in enumerate(layers, 1):
            if typed[i - 1]:
                pages.append(PageExtraction(i, layer, "text_layer", 0.98))
            else:
                pages.append(PageExtraction(i, "", "text_layer", 0.0, is_blank=True))
                warnings.append(f"Page {i} is a picture and was not read")
        return _result(pages, page_count, warnings)

    if phone_text:
        return _from_phone(phone_text)
    return DocumentTextResult([], 0, "unknown", 0.0, [f"Unsupported file format: {ext}"], "")
