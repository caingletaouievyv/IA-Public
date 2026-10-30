# IA/backend/app/notes/tesseract_runtime.py
"""Locate Tesseract for pytesseract (local dev, Docker/Render with tesseract-ocr package)."""

import os
import shutil


class OcrUnavailableError(Exception):
    """Raised when the Tesseract binary or Python OCR dependencies are missing."""


OCR_UNAVAILABLE_MESSAGE = (
    "Image OCR is not available on this server. "
    "Tesseract must be installed (for example tesseract-ocr on Debian/Ubuntu) "
    "or TESSERACT_CMD must point to the tesseract executable."
)


def tesseract_executable() -> str | None:
    """Resolved path to the tesseract binary, or None if not found."""
    configured = (os.environ.get("TESSERACT_CMD") or "").strip()
    if configured:
        return configured
    return shutil.which("tesseract")


def configure_pytesseract() -> None:
    import pytesseract

    exe = tesseract_executable()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe


def is_tesseract_available() -> bool:
    """True when pytesseract can run tesseract --version."""
    try:
        import pytesseract
    except ImportError:
        return False
    configure_pytesseract()
    if not tesseract_executable():
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ensure_tesseract_ready() -> None:
    """Raise OcrUnavailableError when OCR cannot run."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        report = error
        from app.common.understanding_gaps import report_understanding_gap

        report_understanding_gap("notes.image_ocr.unavailable", report)
        raise OcrUnavailableError(OCR_UNAVAILABLE_MESSAGE) from error
    if not is_tesseract_available():
        from app.common.understanding_gaps import report_understanding_gap

        report_understanding_gap(
            "notes.image_ocr.unavailable",
            RuntimeError("tesseract executable not found or not runnable"),
        )
        raise OcrUnavailableError(OCR_UNAVAILABLE_MESSAGE)
