# IA/backend/app/db.py
# SQLAlchemy engine and request-scoped sessions. Account, note, memory, settings, credit, activity, and diagnostics tables are mapped separately.

import inspect
import logging
import re
import sys
import threading
from contextlib import contextmanager

from flask import g, has_app_context
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import database_url as configured_database_url

_engine: Engine | None = None
_engine_lock = threading.Lock()
_log = logging.getLogger("app.db")
_FILTERS_INSTALLED = False
_URL_IN_TEXT = re.compile(r"(?i)[a-z][a-z0-9+]*://\S+")
_USERINFO = re.compile(r"://[^\s/@]+:[^\s/@]+@")
_PASSWORD_QUERY = re.compile(r"(?i)(password|pwd)=([^\s&]+)")
_POSTGRES_DRIVERS = frozenset({"postgresql", "postgresql+psycopg", "postgres"})
_SAFE_CONNECTION_MESSAGE = "Database connection failed"


class DatabaseConfigError(RuntimeError):
    """DATABASE_URL is missing or unsupported. The message must not include connection details."""


class DatabaseConnectionError(RuntimeError):
    """The database could not be reached. The message must not include the URL."""


def database_url() -> str:
    """Return the current backend DATABASE_URL, or an empty string."""
    return configured_database_url()


def validate_database_url(url: str) -> str:
    """Accept postgresql and postgresql+psycopg URLs. Errors omit the URL."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise DatabaseConfigError("DATABASE_URL must be configured")
    try:
        parsed = make_url(cleaned)
    except Exception:
        raise DatabaseConfigError("DATABASE_URL is not a valid database URL") from None
    if parsed.drivername not in _POSTGRES_DRIVERS:
        raise DatabaseConfigError(
            "DATABASE_URL must use the postgresql or postgresql+psycopg scheme"
        ) from None
    return cleaned


def require_database_url() -> str:
    """Return a supported DATABASE_URL or raise without echoing any secret."""
    return validate_database_url(database_url())


def reset_engine() -> None:
    """Drop the cached engine. Used by tests so a new URL can take effect."""
    global _engine
    with _engine_lock:
        engine = _engine
        _engine = None
    if engine is not None:
        engine.dispose()


def install_engine(engine: Engine) -> None:
    """Cache an engine created by the caller. SQLite tests use this."""
    global _engine
    with _engine_lock:
        previous = _engine
        _engine = engine
    if previous is not None and previous is not engine:
        previous.dispose()


def get_engine() -> Engine:
    """Lazy engine. NullPool avoids a second pool in front of Neon's pooler."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            url = require_database_url()
            install_connection_log_filter()
            try:
                _engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
            except Exception as exc:
                _raise_safe(exc)
        return _engine


def open_connection():
    """Open a connection. Driver failures become DatabaseConnectionError."""
    install_connection_log_filter()
    try:
        return get_engine().connect()
    except DatabaseConfigError:
        raise
    except DatabaseConnectionError:
        raise
    except Exception as exc:
        _raise_safe(exc)


@contextmanager
def migration_connection():
    """Alembic online connection. Close it afterward and drop connection secrets."""
    connection = open_connection()
    try:
        yield connection
    except BaseException as exc:
        _reraise_without_secrets(exc)
    finally:
        try:
            connection.close()
        except Exception as exc:
            if sys.exc_info()[0] is None:
                _raise_safe(exc)


def open_session() -> Session:
    """New session bound to the current engine. Caller or teardown must close it."""
    kwargs = {"bind": get_engine(), "autoflush": False, "expire_on_commit": False}
    # SQLAlchemy 2.1 close() resets the session unless this is turned off.
    if "close_resets_only" in inspect.signature(Session.__init__).parameters:
        kwargs["close_resets_only"] = False
    return Session(**kwargs)


def get_request_session() -> Session:
    """Return the session for this app context, creating it on first use."""
    if not has_app_context():
        raise RuntimeError("Database session requires an application context")
    session = g.get("db_session")
    if session is None:
        session = open_session()
        g.db_session = session
    return session


def close_request_session(exc: BaseException | None = None) -> None:
    """Roll back uncommitted work and close. Never commits for the request."""
    if not has_app_context():
        return
    session = g.pop("db_session", None)
    if session is None:
        return
    cleanup_error: BaseException | None = None
    try:
        session.rollback()
    except Exception as rollback_exc:
        cleanup_error = rollback_exc
    try:
        session.close()
    except Exception as close_exc:
        if cleanup_error is None:
            cleanup_error = close_exc
    if exc is not None or cleanup_error is None:
        return
    _raise_safe(cleanup_error)


@contextmanager
def transaction(session: Session):
    """Commit this session on success. Roll back on error. Does not close it."""
    try:
        yield session
    except BaseException:
        _rollback_quietly(session)
        raise
    try:
        session.commit()
    except BaseException as exc:
        _rollback_quietly(session)
        if isinstance(exc, Exception) and _exception_is_sensitive(exc):
            _raise_safe(exc)
        raise


@contextmanager
def session_scope():
    """Commit on success, roll back on error, and permanently close the session."""
    session = open_session()
    try:
        with transaction(session):
            yield session
    finally:
        _close_session(session, preserve=sys.exc_info()[0] is not None)


def check_database() -> bool:
    """Run SELECT 1. Failures omit the connection string and credentials."""
    try:
        with open_connection() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseConfigError:
        raise
    except DatabaseConnectionError:
        raise
    except Exception as exc:
        _raise_safe(exc)
    return True


def redact_database_text(message: str) -> str:
    """Strip URL userinfo, full URLs, and password query values from a message."""
    url = database_url()
    if url and url in message:
        message = message.replace(url, "[redacted]")
    host = _configured_host()
    message = _URL_IN_TEXT.sub("[redacted]", message)
    message = _USERINFO.sub("://[redacted]@", message)
    message = _PASSWORD_QUERY.sub(r"\1=[redacted]", message)
    if host:
        message = message.replace(host, "[redacted]")
    return message


def install_connection_log_filter() -> None:
    """Rewrite SQLAlchemy and Alembic log lines that contain connection details."""
    global _FILTERS_INSTALLED
    if _FILTERS_INSTALLED:
        return
    secret_filter = _ConnectionSecretFilter()
    for name in ("sqlalchemy", "sqlalchemy.engine", "alembic", "alembic.runtime.migration"):
        logging.getLogger(name).addFilter(secret_filter)
    _FILTERS_INSTALLED = True


def init_app(app) -> None:
    """Close any request session when the app context ends. Does not open a connection."""
    install_connection_log_filter()

    @app.teardown_appcontext
    def _close_db_session(exception=None):
        close_request_session(exception)


class _ConnectionSecretFilter(logging.Filter):
    """Replace log messages that include a URL, password, or configured host."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = _record_text(record)
        if _message_is_sensitive(message):
            record.msg = _SAFE_CONNECTION_MESSAGE
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


def _configured_host() -> str:
    url = database_url()
    if not url:
        return ""
    try:
        return make_url(url).host or ""
    except Exception:
        return ""


def _reraise_without_secrets(exc: BaseException) -> None:
    if isinstance(exc, (DatabaseConfigError, DatabaseConnectionError)):
        raise exc
    if isinstance(exc, Exception) and _exception_is_sensitive(exc):
        _raise_safe(exc)
    raise exc


def _record_text(record: logging.LogRecord) -> str:
    try:
        message = record.getMessage()
    except Exception:
        message = ""
    if record.exc_info and record.exc_info[1] is not None:
        message = f"{message} {record.exc_info[1]!r}"
    return message


def _exception_is_sensitive(exc: BaseException) -> bool:
    return _message_is_sensitive(str(exc)) or _message_is_sensitive(repr(exc))


def _message_is_sensitive(message: str) -> bool:
    if not message:
        return False
    lowered = message.lower()
    if "://" in message or "password=" in lowered or "pwd=" in lowered:
        return True
    url = database_url()
    if url and url in message:
        return True
    host = _configured_host()
    return bool(host and host in message)


def _raise_safe(exc: BaseException) -> None:
    """Log a generic failure and raise without the driver exception or its text."""
    del exc
    _log.error(_SAFE_CONNECTION_MESSAGE)
    raise DatabaseConnectionError(_SAFE_CONNECTION_MESSAGE) from None


def _rollback_quietly(session: Session) -> None:
    try:
        session.rollback()
    except Exception:
        return


def _close_session(session: Session, *, preserve: bool) -> None:
    try:
        session.close()
    except Exception as exc:
        if preserve:
            return
        _raise_safe(exc)
