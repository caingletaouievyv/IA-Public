# IA/backend/app/notes/image_to_note.py
"""Convert uploaded images to one note: OCR → concatenate → AI summarize → save or append. Requires Tesseract installed."""

from app.notes.manager import add_note, update_note, find_note_by_title_category
from app.ai.engine import summarize_for_note
from app.common.understanding_gaps import report_understanding_gap

APPEND_SEP = "\n\n---\n\n"

def extract_text_from_images(image_files) -> str:
    """Run OCR on each image; concatenate text. Returns empty string if no text or OCR unavailable."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as error:
        report_understanding_gap("notes.image_ocr.unavailable", error)
        return ""
    texts = []
    for f in image_files:
        if not f or not getattr(f, "read", None):
            continue
        try:
            f.seek(0)
            img = Image.open(f)
            text = pytesseract.image_to_string(img)
            if (text or "").strip():
                texts.append(text.strip())
        except Exception as error:
            report_understanding_gap("notes.image_ocr.image_failed", error)
    return "\n\n".join(texts) if texts else ""

def process_images_to_note(image_files, title: str, category: str, tags: list | None = None, user_id: str = None):
    """OCR images → concatenate → AI summarize → add_note or append to existing note with same title+category. user_id required (Phase 8)."""
    if not user_id:
        raise ValueError("user_id required")
    raw = extract_text_from_images(image_files)
    if not raw.strip():
        raise ValueError("No text extracted from images. Check image format and Tesseract installation.")
    content = summarize_for_note(raw)
    if not content.strip():
        report_understanding_gap("notes.image_summary.empty")
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
