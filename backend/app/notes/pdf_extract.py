# IA/backend/app/notes/pdf_extract.py
"""Extract plain text from text-based PDF uploads. No OCR, storage, or AI."""

import io
from dataclasses import dataclass

from app.config import NOTES_MAX_CONTENT_CHARS, NOTES_PDF_MAX_BYTES
from app.common.understanding_gaps import report_understanding_gap

PDF_MAGIC = b"%PDF"


class PdfExtractError(ValueError):
    """User-safe PDF extraction failure."""


@dataclass(frozen=True)
class PdfExtractResult:
    text: str
    page_count: int


def _filename_looks_like_pdf(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    return name.endswith(".pdf")


def _read_pdf_bytes(file_storage) -> bytes:
    if not file_storage or not getattr(file_storage, "read", None):
        raise PdfExtractError("Upload a PDF file (.pdf).")
    if not _filename_looks_like_pdf(getattr(file_storage, "filename", None)):
        raise PdfExtractError("Upload a PDF file (.pdf).")
    try:
        file_storage.seek(0)
        data = file_storage.read(NOTES_PDF_MAX_BYTES + 1)
    except OSError as error:
        report_understanding_gap("notes.pdf_extract.read_failed", error)
        raise PdfExtractError("Could not read the uploaded file.") from error
    if not data:
        raise PdfExtractError("The uploaded file is empty.")
    if len(data) > NOTES_PDF_MAX_BYTES:
        raise PdfExtractError("PDF exceeds the 15 MB size limit.")
    if not data.lstrip().startswith(PDF_MAGIC):
        raise PdfExtractError("Invalid or unsupported PDF file.")
    return data


def extract_text_from_pdf(file_storage, user_id: str | None = None) -> PdfExtractResult:
    """Extract text from one PDF upload. Raises PdfExtractError on invalid input."""
    data = _read_pdf_bytes(file_storage)
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as error:
        report_understanding_gap("notes.pdf_extract.unavailable", error)
        raise PdfExtractError("PDF text extraction is unavailable on this server.") from error

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except PdfReadError as error:
        report_understanding_gap("notes.pdf_extract.parse_failed", error, user_id=user_id)
        raise PdfExtractError("Invalid or unsupported PDF file.") from error
    except Exception as error:
        report_understanding_gap("notes.pdf_extract.parse_failed", error, user_id=user_id)
        raise PdfExtractError("Invalid or unsupported PDF file.") from error

    if getattr(reader, "is_encrypted", False):
        try:
            if reader.decrypt("") == 0:
                raise PdfExtractError(
                    "This PDF is password-protected. Encrypted PDFs are not supported."
                )
        except PdfExtractError:
            raise
        except Exception as error:
            report_understanding_gap("notes.pdf_extract.encrypted", error, user_id=user_id)
            raise PdfExtractError(
                "This PDF is password-protected. Encrypted PDFs are not supported."
            ) from error

    page_count = len(reader.pages)
    if page_count == 0:
        raise PdfExtractError("No text found in this PDF. Image-only or scanned PDFs require OCR, which is not supported.")

    parts: list[str] = []
    for page in reader.pages:
        try:
            chunk = page.extract_text() or ""
        except Exception as error:
            report_understanding_gap("notes.pdf_extract.page_failed", error, user_id=user_id)
            chunk = ""
        if chunk.strip():
            parts.append(chunk.strip())

    text = "\n\n".join(parts).strip()
    if not text:
        raise PdfExtractError(
            "No text found in this PDF. Image-only or scanned PDFs require OCR, which is not supported."
        )
    if len(text) > NOTES_MAX_CONTENT_CHARS:
        raise PdfExtractError(
            f"Extracted text exceeds the {NOTES_MAX_CONTENT_CHARS:,} character limit."
        )
    return PdfExtractResult(text=text, page_count=page_count)
