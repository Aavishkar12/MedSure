"""Uploaded file -> text with [Page N] markers. Uses the PDF text layer where there is one and OCR otherwise.

OCR needs the Tesseract program (https://github.com/tesseract-ocr/tesseract). When it is missing,
scanned pages come back empty with a warning and the vision model reads the page images instead.
"""

import io
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import settings

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp")
TEXT_EXTENSIONS = (".txt",)
OCR_DPI = 200  # Tesseract reads 200-300 dpi best; higher is slow for little gain


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


def _tesseract() -> Tuple[object, Optional[str]]:
    """(pytesseract module, None) when OCR can run, otherwise (None, reason)."""
    try:
        import pytesseract
    except ImportError:
        return None, "OCR is unavailable: the pytesseract package is not installed."
    cmd = settings.tesseract_cmd or shutil.which("tesseract")
    if not cmd:
        return None, "OCR is unavailable: Tesseract is not installed or TESSERACT_CMD is not set."
    pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract, None


def _ocr_image_bytes(data: bytes) -> Tuple[str, float, Optional[str]]:
    """OCR one page image. Returns (text, confidence 0-1, warning)."""
    pytesseract, reason = _tesseract()
    if pytesseract is None:
        return "", 0.0, reason
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as img:
            gray = ImageOps.exif_transpose(img).convert("L")  # phone photos carry their rotation in EXIF
            ocr = pytesseract.image_to_data(gray, lang="eng", output_type=pytesseract.Output.DICT)
    except Exception as e:
        return "", 0.0, f"OCR failed: {type(e).__name__}: {e}"

    # Rebuild lines from Tesseract's word boxes, and average the confidence of the words it kept.
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(ocr["text"]):
        conf = float(ocr["conf"][i])
        if not word.strip() or conf < 0:
            continue
        key = (ocr["block_num"][i], ocr["par_num"][i], ocr["line_num"][i])
        lines.setdefault(key, []).append(word)
        confs.append(conf)
    text = "\n".join(" ".join(words) for words in lines.values())
    confidence = round(sum(confs) / len(confs) / 100, 2) if confs else 0.0
    return text.strip(), confidence, None


def _result(pages: List[PageExtraction], page_count: int, warnings: List[str]) -> DocumentTextResult:
    ocr_pages = sum(p.method == "ocr" for p in pages)
    primary = "ocr" if ocr_pages > len(pages) - ocr_pages else "text_layer"
    confidence = round(sum(p.confidence for p in pages) / len(pages), 2) if pages else 0.0
    full_text = "\n\n".join(f"[Page {p.page_num}]\n{p.text}" for p in pages if p.text)
    return DocumentTextResult(pages, page_count, primary, confidence, warnings, full_text)


def extract_document_text(file_path: str, supplied_text: Optional[str] = None) -> DocumentTextResult:
    """
    Text page by page. supplied_text (OCR done on the phone) wins when it is usable.
    PDFs use their own text layer, and pages without one are rendered and OCR'd. Images are OCR'd.
    """
    if supplied_text and _is_usable_text(supplied_text):
        text = supplied_text.strip()
        if "[Page " not in text:
            text = f"[Page 1]\n{text}"
        page_count = max(text.count("[Page "), 1)
        page = PageExtraction(1, text, method="device_ocr", confidence=0.9)
        return DocumentTextResult([page], page_count, "device_ocr", 0.9, [], text)

    path = Path(file_path) if file_path else None
    if not path or not path.exists():
        return DocumentTextResult([], 0, "unknown", 0.0, ["File not found"], "")

    ext = path.suffix.lower()
    warnings: List[str] = []

    if ext in TEXT_EXTENSIONS:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return _result([PageExtraction(1, text, "text_layer", 1.0, not text)], 1, warnings)

    if ext in IMAGE_EXTENSIONS:
        text, conf, warn = _ocr_image_bytes(path.read_bytes())
        if warn:
            warnings.append(warn)
        return _result([PageExtraction(1, text, "ocr", conf, not text)], 1, warnings)

    if ext == ".pdf":
        try:
            import pymupdf

            pages: List[PageExtraction] = []
            with pymupdf.open(path) as pdf:
                for i, page in enumerate(pdf, start=1):
                    layer = page.get_text().strip()
                    if _is_usable_text(layer):
                        pages.append(PageExtraction(i, layer, "text_layer", 0.98))
                        continue
                    # Scanned page: render it and OCR the picture.
                    png = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
                    text, conf, warn = _ocr_image_bytes(png)
                    if warn and warn not in warnings:
                        warnings.append(warn)
                    if text:
                        pages.append(PageExtraction(i, text, "ocr", conf))
                    else:
                        pages.append(PageExtraction(i, layer, "text_layer", 0.2, is_blank=True))
                        warnings.append(f"Page {i} has no readable text")
                page_count = pdf.page_count
            if page_count == 0:
                warnings.append("PDF contains 0 pages")
            return _result(pages, page_count, warnings)
        except Exception as e:
            return DocumentTextResult([], 0, "text_layer", 0.0, [f"Failed to read PDF: {e}"], "")

    return DocumentTextResult([], 0, "unknown", 0.0, [f"Unsupported file format: {ext}"], "")
