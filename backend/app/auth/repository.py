# IA/backend/app/auth/repository.py
# Account reads and writes. Callers commit through auth_session().

import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.auth.models import DemoSeedMarker, MainAdminMarker, User
from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope

SINGLETON = 1
# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()


class AccountStoreError(RuntimeError):
    """Account storage failed. The message must not include hashes or connection details."""


class AccountConflict(Exception):
    """A unique or lock race lost. The message stays empty so driver text is not exposed."""


def _is_serialization_conflict(error: BaseException) -> bool:
    parts = [str(error)]
    cause = getattr(error, "orig", None) or error.__cause__
    if cause is not None:
        parts.append(str(cause))
    text_value = " ".join(parts).lower()
    return any(
        token in text_value
        for token in (
            "database is locked",
            "database is busy",
            "deadlock detected",
            "could not serialize access",
            "serialization failure",
        )
    )


@contextmanager
def auth_session():
    """Commit one account transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except IntegrityError:
            raise AccountConflict() from None
        except OperationalError as error:
            if _is_serialization_conflict(error):
                raise AccountConflict() from None
            raise AccountStoreError("Could not access accounts.") from None
        except (DatabaseConfigError, DatabaseConnectionError, AccountStoreError):
            raise
        except SQLAlchemyError as error:
            if _is_serialization_conflict(error):
                raise AccountConflict() from None
            raise AccountStoreError("Could not access accounts.") from None


def lock_user_table(session) -> None:
    """Serialize bootstrap on PostgreSQL. SQLite tests do not prove this lock."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))


def count_users(session) -> int:
    return len(session.scalars(select(User.user_id)).all())


def find_by_username(session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def find_by_id(session, user_id: str) -> User | None:
    return session.get(User, user_id)


def insert_user(session, *, user_id: str, username: str, password_hash: str, role: str) -> User:
    user = User(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def set_role(session, user_id: str, role: str) -> User:
    user = find_by_id(session, user_id)
    if user is None:
        raise ValueError("User not found")
    user.role = role
    session.flush()
    return user


def list_users(session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username, User.user_id)))


def main_admin_ids(session) -> list[str]:
    return list(
        session.scalars(select(User.user_id).where(User.role == "main_admin")).all()
    )


def marker_view(session) -> dict | None:
    row = session.scalar(select(MainAdminMarker).where(MainAdminMarker.singleton == SINGLETON))
    if row is None:
        return None
    user = find_by_id(session, row.user_id)
    if user is None:
        return None
    return {
        "username": user.username,
        "user_id": user.user_id,
        "created_at": _created_text(row.created_at),
    }


def insert_main_admin_marker(session, user_id: str) -> None:
    session.add(MainAdminMarker(singleton=SINGLETON, user_id=user_id))
    session.flush()


def demo_marker_user_id(session) -> str | None:
    return session.scalar(
        select(DemoSeedMarker.user_id).where(DemoSeedMarker.singleton == SINGLETON)
    )


def insert_demo_marker(session, user_id: str) -> None:
    session.add(DemoSeedMarker(singleton=SINGLETON, user_id=user_id))
    session.flush()


def user_record(user: User) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "password_hash": user.password_hash,
        "role": user.role,
    }


def replace_users(session, payloads: list[dict]) -> None:
    """Replace account rows for tests and maintenance. Stored hashes are kept as given."""
    if not payloads:
        session.execute(delete(DemoSeedMarker))
        session.execute(delete(MainAdminMarker))
        session.execute(delete(User))
        return
    incoming = {item["user_id"]: item for item in payloads}
    existing = {user.user_id: user for user in session.scalars(select(User))}
    for user_id in set(existing) - set(incoming):
        session.execute(delete(DemoSeedMarker).where(DemoSeedMarker.user_id == user_id))
        session.execute(delete(MainAdminMarker).where(MainAdminMarker.user_id == user_id))
        session.delete(existing[user_id])
    session.flush()
    for payload in payloads:
        row = existing.get(payload["user_id"])
        username = (payload.get("username") or "").strip()
        password_hash = payload.get("password_hash") or ""
        role = payload.get("role") or "user"
        if row is None:
            insert_user(
                session,
                user_id=payload["user_id"],
                username=username,
                password_hash=password_hash,
                role=role,
            )
        else:
            row.username = username
            row.password_hash = password_hash
            row.role = role
    session.flush()


def _created_text(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
