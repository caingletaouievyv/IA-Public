# IA/backend/app/notes/create_pending.py
# Per-user pending note creation. The row lives in PostgreSQL and is not a JSON file.

import datetime

from app.notes import pending_repository as repository

TTL_SECONDS = 900


def set_pending_create(
    user_id: str,
    *,
    need_title: bool,
    need_content: bool,
    title: str | None = None,
    category: str | None = None,
) -> dict:
    if not user_id:
        raise ValueError("Pending create requires user_id")
    cleaned_title = (title or "").strip() or None
    cleaned_category = (category or "").strip() or "general"
    with repository.pending_session() as session:
        return repository.save_create(
            session,
            user_id,
            need_title=bool(need_title),
            need_content=bool(need_content),
            title=cleaned_title,
            category=cleaned_category,
            ttl_seconds=TTL_SECONDS,
        )


def get_pending_create(user_id: str) -> dict | None:
    if not user_id:
        return None
    with repository.pending_session() as session:
        return repository.load_pending(session, user_id, repository.KIND_CREATE)


def consume_pending_create(user_id: str) -> dict | None:
    """Delete the live create confirmation. A second consumer receives nothing."""
    if not user_id:
        return None
    with repository.pending_session() as session:
        return repository.consume_pending(session, user_id, repository.KIND_CREATE)


def restore_pending_create(user_id: str, payload: dict) -> None:
    """Put a consumed create confirmation back when note creation did not succeed."""
    if not user_id or not payload:
        return
    with repository.pending_session() as session:
        repository.save_create(
            session,
            user_id,
            need_title=bool(payload.get("need_title")),
            need_content=bool(payload.get("need_content")),
            title=payload.get("title"),
            category=payload.get("category") or "general",
            ttl_seconds=TTL_SECONDS,
            created_at=_from_epoch(payload.get("created_at")),
            expires_at=_from_epoch(payload.get("expires_at")),
        )


def clear_pending_create(user_id: str) -> None:
    if not user_id:
        return
    with repository.pending_session() as session:
        repository.clear_pending(session, user_id, repository.KIND_CREATE)


def _from_epoch(value) -> datetime.datetime | None:
    if value is None:
        return None
    return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
