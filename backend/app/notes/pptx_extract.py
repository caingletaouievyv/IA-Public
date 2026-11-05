# IA/backend/app/notes/pptx_extract.py
"""Extract plain text from PowerPoint uploads. No OCR, storage, or AI."""

import io
import zipfile
from dataclasses import dataclass

from app.config import NOTES_MAX_CONTENT_CHARS, NOTES_PPTX_MAX_BYTES
from app.common.understanding_gaps import report_understanding_gap

PPTX_MAGIC = b"PK"


class PptxExtractError(ValueError):
    """User-safe PowerPoint extraction failure."""


@dataclass(frozen=True)
class PptxExtractResult:
    text: str
    slide_count: int


def _filename_looks_like_pptx(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    return name.endswith(".pptx")


def _read_pptx_bytes(file_storage) -> bytes:
    if not file_storage or not getattr(file_storage, "read", None):
        raise PptxExtractError("Upload a PowerPoint file (.pptx).")
    if not _filename_looks_like_pptx(getattr(file_storage, "filename", None)):
        raise PptxExtractError("Upload a PowerPoint file (.pptx).")
    try:
        file_storage.seek(0)
        data = file_storage.read(NOTES_PPTX_MAX_BYTES + 1)
    except OSError as error:
        report_understanding_gap("notes.pptx_extract.read_failed", error)
        raise PptxExtractError("Could not read the uploaded file.") from error
    if not data:
        raise PptxExtractError("The uploaded file is empty.")
    if len(data) > NOTES_PPTX_MAX_BYTES:
        raise PptxExtractError("PowerPoint exceeds the 15 MB size limit.")
    if not data.startswith(PPTX_MAGIC):
        raise PptxExtractError("Invalid or unsupported PowerPoint file.")
    return data


def _shape_lines(shape) -> list[str]:
    """Collect visible text in shape order. Pictures and charts are skipped."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        lines = []
        for child in shape.shapes:
            lines.extend(_shape_lines(child))
        return lines
    if getattr(shape, "has_table", False):
        lines = []
        for row in shape.table.rows:
            cells = [(cell.text or "").strip() for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if cells:
                lines.append(" | ".join(cells))
        return lines
    if getattr(shape, "has_text_frame", False):
        lines = []
        for paragraph in shape.text_frame.paragraphs:
            line = (paragraph.text or "").strip()
            if line:
                lines.append(line)
        return lines
    return []


def _slide_lines(slide) -> list[str]:
    lines = []
    for shape in slide.shapes:
        lines.extend(_shape_lines(shape))
    if getattr(slide, "has_notes_slide", False):
        notes = (slide.notes_slide.notes_text_frame.text or "").strip()
        if notes and notes.lower() != "click to add notes":
            lines.append(f"Speaker notes: {notes}")
    return lines


def extract_text_from_pptx(file_storage, user_id: str | None = None) -> PptxExtractResult:
    """Extract slide text in presentation order. Raises PptxExtractError on invalid input."""
    data = _read_pptx_bytes(file_storage)
    try:
        from pptx import Presentation
        from pptx.exc import PackageNotFoundError
    except ImportError as error:
        report_understanding_gap("notes.pptx_extract.unavailable", error)
        raise PptxExtractError("PowerPoint text extraction is unavailable on this server.") from error

    try:
        presentation = Presentation(io.BytesIO(data))
    except (PackageNotFoundError, zipfile.BadZipFile, OSError, ValueError) as error:
        report_understanding_gap("notes.pptx_extract.parse_failed", error, user_id=user_id)
        raise PptxExtractError("Invalid or unsupported PowerPoint file.") from error
    except Exception as error:
        report_understanding_gap("notes.pptx_extract.parse_failed", error, user_id=user_id)
        raise PptxExtractError("Invalid or unsupported PowerPoint file.") from error

    blocks = []
    included = 0
    for index, slide in enumerate(presentation.slides, start=1):
        try:
            lines = _slide_lines(slide)
        except Exception as error:
            report_understanding_gap("notes.pptx_extract.slide_failed", error, user_id=user_id)
            lines = []
        if not lines:
            continue
        included += 1
        blocks.append(f"--- Slide {index} ---\n" + "\n".join(lines))

    text = "\n\n".join(blocks).strip()
    if not text:
        raise PptxExtractError(
            "No text found in this PowerPoint. Slides that contain only images are not transcribed."
        )
    if len(text) > NOTES_MAX_CONTENT_CHARS:
        raise PptxExtractError(
            f"Extracted text exceeds the {NOTES_MAX_CONTENT_CHARS:,} character limit."
        )
    return PptxExtractResult(text=text, slide_count=included)
