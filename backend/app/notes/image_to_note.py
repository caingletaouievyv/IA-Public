# IA/backend/app/notes/image_to_note.py
"""OCR uploaded images. Review extract returns text only; the legacy path can summarize and save."""

import io
import os
from dataclasses import dataclass

from app.ai.engine import summarize_for_note
from app.common.understanding_gaps import report_understanding_gap
from app.config import NOTES_IMAGE_MAX_BYTES, NOTES_IMAGE_MAX_COUNT, NOTES_IMAGE_MAX_TOTAL_BYTES, NOTES_MAX_CONTENT_CHARS
from app.notes.manager import add_note, find_note_by_title_category, update_note
from app.notes.tesseract_runtime import configure_pytesseract, ensure_tesseract_ready

APPEND_SEP = "\n\n---\n\n"
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class ImageExtractError(ValueError):
    """User-safe screenshot extraction failure."""


@dataclass(frozen=True)
class ImageExtractResult:
    text: str
    image_count: int


def _image_name(file_storage, index: int) -> str:
    name = (getattr(file_storage, "filename", None) or "").strip()
    return name or f"image {index}"


def _prepare_images(image_files) -> list[tuple[str, bytes]]:
    """Validate upload order, type, and size. Return filename/bytes pairs."""
    files = [item for item in image_files or [] if item and getattr(item, "filename", None)]
    if not files:
        raise ImageExtractError("Upload one or more screenshot images.")
    if len(files) > NOTES_IMAGE_MAX_COUNT:
        raise ImageExtractError(f"Upload at most {NOTES_IMAGE_MAX_COUNT} images at a time.")
    prepared = []
    total = 0
    for index, file_storage in enumerate(files, start=1):
        name = _image_name(file_storage, index)
        extension = os.path.splitext(name)[1].lower()
        if extension not in _IMAGE_EXTENSIONS:
            raise ImageExtractError("Upload screenshot images (.png, .jpg, .jpeg, .webp, .gif, or .bmp).")
        try:
            file_storage.seek(0)
            data = file_storage.read(NOTES_IMAGE_MAX_BYTES + 1)
        except OSError as error:
            report_understanding_gap("notes.image_ocr.read_failed", error)
            raise ImageExtractError(f"Could not read {name}.") from error
        if not data:
            raise ImageExtractError(f"{name} is empty.")
        if len(data) > NOTES_IMAGE_MAX_BYTES:
            raise ImageExtractError(f"{name} exceeds the 8 MB image size limit.")
        total += len(data)
        if total > NOTES_IMAGE_MAX_TOTAL_BYTES:
            raise ImageExtractError("Images exceed the 32 MB total size limit.")
        prepared.append((name, data))
    return prepared


def extract_text_from_images(image_files, user_id: str | None = None) -> ImageExtractResult:
    """OCR each image in upload order. A missing Tesseract install raises OcrUnavailableError."""
    prepared = _prepare_images(image_files)
    ensure_tesseract_ready()
    configure_pytesseract()
    import pytesseract
    from PIL import Image

    texts = []
    for name, data in prepared:
        try:
            image = Image.open(io.BytesIO(data))
            text = pytesseract.image_to_string(image)
        except Exception as error:
            report_understanding_gap("notes.image_ocr.image_failed", error, user_id=user_id)
            continue
        cleaned = (text or "").strip()
        if cleaned:
            texts.append(cleaned)
    text = "\n\n".join(texts)
    if len(text) > NOTES_MAX_CONTENT_CHARS:
        raise ImageExtractError(
            f"Extracted text exceeds the {NOTES_MAX_CONTENT_CHARS:,} character limit."
        )
    return ImageExtractResult(text=text, image_count=len(texts))


def _extracted_text(extracted) -> str:
    if isinstance(extracted, str):
        return extracted
    return extracted.text or ""


def process_images_to_note(image_files, title: str, category: str, tags: list | None = None, user_id: str = None):
    """OCR images, summarize with AI, then add or append a note. This is not the Add Note import path."""
    if not user_id:
        raise ValueError("user_id required")
    raw = _extracted_text(extract_text_from_images(image_files, user_id=user_id))
    if not raw.strip():
        raise ValueError("No text extracted from images. Check image format and Tesseract installation.")
    content = summarize_for_note(raw)
    if not content.strip():
        report_understanding_gap("notes.image_summary.empty", user_id=user_id)
        content = raw[:5000]
    content = content.strip()
    title = title.strip() or "Untitled"
    category = category.strip() or "general"
    existing = find_note_by_title_category(title, category, user_id)
    if existing:
        new_content = (existing.get("content") or "").strip() + APPEND_SEP + content
        updated = update_note(existing["id"], {"content": new_content}, user_id)
        return updated, True
    return add_note({
        "title": title,
        "category": category,
        "content": content,
        "tags": list(tags) if tags else [],
    }, user_id), False
