# IA/backend/app/notes/delete_pending.py
# Per-user pending note deletion. The row lives in PostgreSQL and is not a JSON file.

from app.notes import pending_repository as repository

TTL_SECONDS = 900


def set_pending_delete(user_id: str, note_id: str, expected_title: str) -> dict:
    if not user_id or not note_id or not (expected_title or "").strip():
        raise ValueError("Pending delete requires user_id, note_id, and expected_title")
    with repository.pending_session() as session:
        return repository.save_delete(
            session,
            user_id,
            note_id=note_id,
            expected_title=expected_title,
            ttl_seconds=TTL_SECONDS,
        )


def get_pending_delete(user_id: str) -> dict | None:
    if not user_id:
        return None
    with repository.pending_session() as session:
        return repository.load_pending(session, user_id, repository.KIND_DELETE)


def consume_pending_delete(user_id: str, *, match_title: str | None = None) -> dict | None:
    """Delete the live delete confirmation. A second consumer receives nothing."""
    if not user_id:
        return None
    with repository.pending_session() as session:
        return repository.consume_pending(
            session,
            user_id,
            repository.KIND_DELETE,
            match_title=match_title,
        )


def clear_pending_delete(user_id: str) -> None:
    if not user_id:
        return
    with repository.pending_session() as session:
        repository.clear_pending(session, user_id, repository.KIND_DELETE)
