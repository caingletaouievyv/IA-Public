# IA/backend/scripts/test/notes_db.py
# SQLite notes tables for tests. Notes share the auth metadata and require a user row.

from scripts.test.auth_db import close_sqlite_auth_database, install_sqlite_auth_database


def install_notes_database():
    """Install the shared in-memory database and create account and note tables."""
    return install_sqlite_auth_database()


def close_notes_database() -> None:
    close_sqlite_auth_database()


def ensure_note_owner(user_id: str) -> str:
    """Insert a user row so a note can reference it. The username is the user id."""
    from app.auth import repository

    with repository.auth_session() as session:
        if repository.find_by_id(session, user_id) is not None:
            return user_id
        repository.insert_user(
            session,
            user_id=user_id,
            username=user_id,
            password_hash="test-hash",
            role="user",
        )
    return user_id
