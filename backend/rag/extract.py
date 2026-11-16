"""PDF text extraction, page by page."""

import io
from dataclasses import dataclass


@dataclass
class Page:
    number: int  # 1-based
    text: str


class PdfError(Exception):
    pass


def extract_pages(pdf_bytes: bytes) -> list[Page]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise PdfError("pypdf is not installed") from exc

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [Page(number=i + 1, text=(page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
    except Exception as exc:
        raise PdfError(f"Could not read PDF: {exc}") from exc


def blank_pages(pages: list[Page]) -> list[int]:
    """Pages with no extractable text -- scans that need OCR. Surfaced rather
    than silently ingesting nothing."""
    return [p.number for p in pages if not p.text]
