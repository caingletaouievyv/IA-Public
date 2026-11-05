# IA/backend/app/notes/routes.py
# Notes CRUD: per-user (Phase 8). Create, list, get, update, delete; create from images.

import json
import logging

from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from app import limiter
from app.config import NOTES_MAX_CONTENT_CHARS
from app.activity.manager import record_activity
from app.activity.repository import ActivityStoreError
from app.common.auth import require_auth, auth_debug
from app.notes.manager import (
    NoteStoreError,
    add_note,
    update_note,
    get_notes_list,
    get_note,
    delete_note,
    get_categories,
    get_tags,
    is_flashcard_deck_category,
)
from app.notes.schemas import NoteCreate, NoteUpdate
from app.notes.image_to_note import ImageExtractError, extract_text_from_images, process_images_to_note
from app.notes.pdf_extract import PdfExtractError, extract_text_from_pdf
from app.notes.pptx_extract import PptxExtractError, extract_text_from_pptx
from app.notes.tesseract_runtime import OcrUnavailableError

logger = logging.getLogger(__name__)


def _validation_response(error: ValidationError):
    """Return the existing validation payload. Fall back when a validator exception is not JSON."""
    payload = error.errors()
    try:
        json.dumps(payload)
    except TypeError:
        payload = json.loads(error.json())
    return jsonify({"error": payload}), 400


def _model_to_dict(model, exclude_none=False):
    """Pydantic v1 .dict() / v2 .model_dump() compatibility."""
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(exclude_none=exclude_none)


def _note_activity_type(action: str, note: dict | None, previous_note: dict | None = None) -> str | None:
    notes = [item for item in (note, previous_note) if item]
    if not notes or any(item.get("category") == "_history" for item in notes):
        return None
    prefix = "flashcard_deck" if any(is_flashcard_deck_category(item.get("category")) for item in notes) else "note"
    return f"{prefix}.{action}"


def _record_note_activity(user_id: str, action: str, note: dict | None, previous_note: dict | None = None):
    event_type = _note_activity_type(action, note, previous_note)
    if event_type is None:
        return
    try:
        record_activity(user_id, event_type)
    except (OSError, ValueError, ActivityStoreError) as error:
        logger.error(
            "activity_event_write_failed event_type=%s error_type=%s",
            event_type,
            type(error).__name__,
        )


bp = Blueprint("notes", __name__)

@bp.route("/auth-check", methods=["GET"])
def notes_auth_check():
    """Debug: returns auth_ok, header_received, lengths. No secret leaked."""
    return auth_debug()

@bp.route("/meta", methods=["GET"])
def notes_meta():
    """Returns { categories, tags } from user's notes for autocomplete/combobox. Auth required."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    try:
        return jsonify({"categories": get_categories(user_id), "tags": get_tags(user_id)})
    except NoteStoreError:
        return jsonify({"error": "Failed to load meta", "detail": "Could not access notes."}), 500
    except Exception as e:
        return jsonify({"error": "Failed to load meta", "detail": str(e)}), 500

@bp.route("/", methods=["POST"], strict_slashes=False)
def create_note():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    try:
        data = request.get_json()
        note_in = NoteCreate(**data)
    except ValidationError as e:
        return _validation_response(e)
    if len(note_in.content) > NOTES_MAX_CONTENT_CHARS:
        return jsonify({
            "error": f"Note content exceeds the {NOTES_MAX_CONTENT_CHARS:,} character limit.",
        }), 400
    new_note = add_note(_model_to_dict(note_in), user_id)
    _record_note_activity(user_id, "created", new_note)
    return jsonify(new_note), 201

@bp.route("/from-pdf/extract", methods=["POST"])
@limiter.limit("10 per minute")
def extract_note_text_from_pdf():
    """Multipart: file (single PDF). Returns extracted text for client review; does not create a note."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    files = request.files.getlist("file") or request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        files = [single] if single and getattr(single, "filename", None) else []
    file_storage = next((f for f in files if f and getattr(f, "filename", None)), None)
    if not file_storage:
        return jsonify({"error": "Missing 'file' in multipart form"}), 400
    if len([f for f in files if f and getattr(f, "filename", None)]) > 1:
        return jsonify({"error": "Upload one PDF at a time."}), 400
    try:
        result = extract_text_from_pdf(file_storage, user_id=user_id)
        return jsonify({
            "text": result.text,
            "page_count": result.page_count,
            "char_count": len(result.text),
        })
    except PdfExtractError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        logger.error("pdf_extract_failed error_type=%s", type(error).__name__)
        return jsonify({"error": "PDF extraction failed."}), 500


@bp.route("/from-pptx/extract", methods=["POST"])
@limiter.limit("10 per minute")
def extract_note_text_from_pptx():
    """Multipart: file (single PPTX). Returns extracted text for client review; does not create a note."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    files = request.files.getlist("file") or request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        files = [single] if single and getattr(single, "filename", None) else []
    file_storage = next((item for item in files if item and getattr(item, "filename", None)), None)
    if not file_storage:
        return jsonify({"error": "Missing 'file' in multipart form"}), 400
    if len([item for item in files if item and getattr(item, "filename", None)]) > 1:
        return jsonify({"error": "Upload one PowerPoint at a time."}), 400
    try:
        result = extract_text_from_pptx(file_storage, user_id=user_id)
        return jsonify({
            "text": result.text,
            "slide_count": result.slide_count,
            "char_count": len(result.text),
        })
    except PptxExtractError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        logger.error("pptx_extract_failed error_type=%s", type(error).__name__)
        return jsonify({"error": "PowerPoint extraction failed."}), 500


def _image_extract_payload(extracted):
    """Accept the extract result, or a plain string from older test doubles."""
    if isinstance(extracted, str):
        text = extracted.strip()
        image_count = 1 if text else 0
    else:
        text = (extracted.text or "").strip()
        image_count = extracted.image_count
    return text, image_count


@bp.route("/from-images/extract", methods=["POST"])
@limiter.limit("10 per minute")
def extract_note_text_from_images():
    """Multipart: image files. OCR only — returns text for client review; does not create a note."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    files = request.files.getlist("files") or request.files.getlist("file") or (
        [request.files.get("file")] if request.files.get("file") else []
    )
    if not files or not any(f and getattr(f, "filename", None) for f in files):
        return jsonify({"error": "Missing 'files' or 'file' in multipart form"}), 400
    try:
        text, image_count = _image_extract_payload(extract_text_from_images(files, user_id=user_id))
        if not text:
            return jsonify({"error": "No text extracted from images. Check format and Tesseract installation."}), 400
        if len(text) > NOTES_MAX_CONTENT_CHARS:
            return jsonify({
                "error": f"Extracted text exceeds the {NOTES_MAX_CONTENT_CHARS:,} character limit.",
            }), 400
        return jsonify({"text": text, "char_count": len(text), "image_count": image_count}), 200
    except OcrUnavailableError as error:
        return jsonify({"error": str(error)}), 503
    except ImageExtractError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        logger.error("image_extract_failed error_type=%s", type(error).__name__)
        return jsonify({"error": "Image text extraction failed."}), 500


@bp.route("/from-images", methods=["POST"])
@limiter.limit("10 per minute")
def create_note_from_images():
    """Multipart: title, category, files. OCR → AI summarize → one note or append. Auth required."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    title = (request.form.get("title") or "").strip() or "Untitled"
    category = (request.form.get("category") or "").strip() or "general"
    files = request.files.getlist("files") or request.files.getlist("file") or ([request.files.get("file")] if request.files.get("file") else [])
    if not files or not any(f and getattr(f, "filename", None) for f in files):
        return jsonify({"error": "Missing 'files' or 'file' in multipart form"}), 400
    try:
        note, appended = process_images_to_note(files, title=title, category=category, tags=[], user_id=user_id)
        _record_note_activity(user_id, "updated" if appended else "created", note)
        return jsonify({"note": note, "appended": appended}), 201
    except OcrUnavailableError as error:
        return jsonify({"error": str(error)}), 503
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except NoteStoreError:
        return jsonify({"error": "Could not access notes."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/", methods=["GET"], strict_slashes=False)
def list_notes():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    try:
        limit = request.args.get("limit", type=int)
    except (TypeError, ValueError):
        limit = None
    try:
        notes = get_notes_list(
            user_id,
            category=request.args.get("category"),
            tag=request.args.get("tag"),
            limit=limit,
        )
    except NoteStoreError:
        return jsonify({"error": "Failed to load notes", "detail": "Could not access notes."}), 500
    except Exception as e:
        return jsonify({"error": "Failed to load notes", "detail": str(e)}), 500
    return jsonify(notes)

@bp.route("/<string:note_id>", methods=["GET"])
def get_note_detail(note_id):
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    note = get_note(note_id, user_id)
    if note:
        return jsonify(note)
    return jsonify({"error": "Note not found"}), 404

@bp.route("/<string:note_id>", methods=["PUT"])
def edit_note(note_id):
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    try:
        data = request.get_json()
        note_update = NoteUpdate(**data)
    except ValidationError as e:
        return _validation_response(e)
    previous_note = get_note(note_id, user_id)
    updated_note = update_note(note_id, _model_to_dict(note_update, exclude_none=True), user_id)
    if updated_note:
        _record_note_activity(user_id, "updated", updated_note, previous_note)
        return jsonify(updated_note)
    return jsonify({"error": "Note not found"}), 404

@bp.route("/<string:note_id>", methods=["DELETE"])
def delete_note_route(note_id):
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    note = get_note(note_id, user_id)
    if not delete_note(note_id, user_id):
        return jsonify({"error": "Note not found"}), 404
    _record_note_activity(user_id, "deleted", note)
    return jsonify({"message": "Note deleted"}), 200
