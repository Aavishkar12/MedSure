import os
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

from ..config import settings


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
        full_text: str
    ):
        self.pages = pages
        self.page_count = page_count
        self.primary_method = primary_method
        self.confidence = confidence
        self.warnings = warnings
        self.full_text = full_text


def _is_usable_text(text: str) -> bool:
    """A page has usable text if it has at least 30 non-whitespace characters."""
    stripped = "".join(text.split())
    return len(stripped) >= 30


def _ocr_image_file(image_path: Path, tesseract_cmd: Optional[str] = None) -> Tuple[str, float, Optional[str]]:
    """Runs OCR on an image file. Returns (text, confidence, warning)."""
    if not pytesseract:
        return "", 0.0, "pytesseract library not available for OCR."

    cmd = tesseract_cmd or settings.tesseract_cmd or shutil.which("tesseract")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    else:
        return "", 0.0, "Tesseract executable not found in PATH or configuration."

    try:
        with Image.open(image_path) as img:
            # Basic preprocessing: grayscale
            gray = img.convert("L")
            text = pytesseract.image_to_string(gray, lang="eng")
            return text.strip(), 0.85, None
    except Exception as e:
        return "", 0.0, f"OCR processing failed: {type(e).__name__}"


def extract_document_text(file_path: str) -> DocumentTextResult:
    """
    Extracts text page-by-page from a PDF or image file.
    Prefers direct digital PDF text layer. Falls back to OCR when text layer is absent or for image files.
    """
    path = Path(file_path)
    if not path.exists():
        return DocumentTextResult(
            pages=[],
            page_count=0,
            primary_method="unknown",
            confidence=0.0,
            warnings=["File not found"],
            full_text=""
        )

    ext = path.suffix.lower()
    pages: List[PageExtraction] = []
    warnings: List[str] = []

    # 1. Image formats (direct OCR path)
    if ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        text, conf, warn = _ocr_image_file(path)
        if warn:
            warnings.append(warn)
        page = PageExtraction(page_num=1, text=text, method="ocr", confidence=conf, is_blank=not bool(text))
        pages.append(page)
        full_text = f"[Page 1]\n{text}" if text else ""
        return DocumentTextResult(
            pages=pages,
            page_count=1,
            primary_method="ocr",
            confidence=conf,
            warnings=warnings,
            full_text=full_text
        )

    # 2. PDF Documents
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            total_pages = len(reader.pages)
            if total_pages == 0:
                warnings.append("PDF contains 0 pages")
                return DocumentTextResult([], 0, "text_layer", 0.0, warnings, "")

            ocr_pages_count = 0
            text_pages_count = 0

            for i, page_obj in enumerate(reader.pages, start=1):
                try:
                    page_text = page_obj.extract_text() or ""
                except Exception as ex:
                    page_text = ""
                    warnings.append(f"Page {i} text layer extraction failed: {str(ex)}")

                if _is_usable_text(page_text):
                    pages.append(PageExtraction(page_num=i, text=page_text.strip(), method="text_layer", confidence=0.98))
                    text_pages_count += 1
                else:
                    # Page lacks usable text layer, needs OCR fallback
                    # Check if images exist on this PDF page
                    page_ocr_text = ""
                    ocr_conf = 0.0
                    ocr_warn = None

                    # If page has embedded images, attempt OCR on them
                    if hasattr(page_obj, "images") and len(page_obj.images) > 0:
                        try:
                            # Try OCR on first main image of page
                            first_img = page_obj.images[0]
                            from io import BytesIO
                            img_bytes = BytesIO(first_img.data)
                            with Image.open(img_bytes) as img:
                                gray = img.convert("L")
                                if pytesseract and (settings.tesseract_cmd or shutil.which("tesseract")):
                                    if settings.tesseract_cmd:
                                        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
                                    page_ocr_text = pytesseract.image_to_string(gray, lang="eng").strip()
                                    ocr_conf = 0.8
                                else:
                                    ocr_warn = f"Page {i} lacks text layer and Tesseract OCR is unavailable"
                        except Exception as ocr_ex:
                            ocr_warn = f"Page {i} OCR attempt error: {type(ocr_ex).__name__}"
                    else:
                        ocr_warn = f"Page {i} has little or no usable text layer"

                    if ocr_warn:
                        warnings.append(ocr_warn)

                    if page_ocr_text:
                        pages.append(PageExtraction(page_num=i, text=page_ocr_text, method="ocr", confidence=ocr_conf))
                        ocr_pages_count += 1
                    else:
                        pages.append(PageExtraction(page_num=i, text=page_text.strip(), method="text_layer", confidence=0.2, is_blank=True))

            # Determine dominant extraction method & overall confidence
            if ocr_pages_count > text_pages_count:
                primary_method = "ocr"
            else:
                primary_method = "text_layer"

            avg_conf = sum(p.confidence for p in pages) / max(len(pages), 1)

            # Build structured text with page boundaries
            formatted_pages = []
            for p in pages:
                if p.text:
                    formatted_pages.append(f"[Page {p.page_num}]\n{p.text}")
                else:
                    formatted_pages.append(f"[Page {p.page_num}]\n(No usable text)")
            full_text = "\n\n".join(formatted_pages)

            return DocumentTextResult(
                pages=pages,
                page_count=total_pages,
                primary_method=primary_method,
                confidence=round(avg_conf, 2),
                warnings=warnings,
                full_text=full_text
            )

        except Exception as e:
            warnings.append(f"Failed to read PDF: {str(e)}")
            return DocumentTextResult([], 0, "text_layer", 0.0, warnings, "")

    # Unsupported file extension
    warnings.append(f"Unsupported file format: {ext}")
    return DocumentTextResult([], 0, "unknown", 0.0, warnings, "")
