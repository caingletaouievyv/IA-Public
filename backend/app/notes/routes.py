# IA/backend/app/notes/routes.py
# Notes CRUD: per-user (Phase 8). Create, list, get, update, delete; create from images.

import logging

from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from app import limiter
from app.activity.manager import record_activity
from app.common.auth import require_auth, auth_debug
from app.notes.manager import add_note, update_note, get_notes_list, get_note, delete_note, get_categories, get_tags
from app.notes.schemas import NoteCreate, NoteUpdate
from app.notes.image_to_note import process_images_to_note

logger = logging.getLogger(__name__)


def _model_to_dict(model, exclude_none=False):
    """Pydantic v1 .dict() / v2 .model_dump() compatibility."""
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(exclude_none=exclude_none)


def _note_activity_type(action: str, note: dict | None, previous_note: dict | None = None) -> str | None:
    notes = [item for item in (note, previous_note) if item]
    if not notes or any(item.get("category") == "_history" for item in notes):
        return None
    prefix = "flashcard_deck" if any(item.get("category") == "flashcards" for item in notes) else "note"
    return f"{prefix}.{action}"


def _record_note_activity(user_id: str, action: str, note: dict | None, previous_note: dict | None = None):
    event_type = _note_activity_type(action, note, previous_note)
    if event_type is None:
        return
    try:
        record_activity(user_id, event_type)
    except (OSError, ValueError) as error:
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
        return jsonify({"error": e.errors()}), 400
    new_note = add_note(_model_to_dict(note_in), user_id)
    _record_note_activity(user_id, "created", new_note)
    return jsonify(new_note), 201

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
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": e.errors()}), 400
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
