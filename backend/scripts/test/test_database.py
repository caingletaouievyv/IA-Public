# IA/backend/scripts/test/test_database.py
# PostgreSQL foundation checks. SQLite covers sessions only; nothing here connects to PostgreSQL.

import logging
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.pool import NullPool, StaticPool

from app.config import database_url as config_database_url
from app.db import (
    DatabaseConfigError,
    DatabaseConnectionError,
    check_database,
    close_request_session,
    database_url,
    get_engine,
    get_request_session,
    open_session,
    init_app,
    install_connection_log_filter,
    install_engine,
    migration_connection,
    open_connection,
    redact_database_text,
    require_database_url,
    reset_engine,
    session_scope,
    transaction,
    validate_database_url,
)

_SECRET = "super-secret-password"
_HOST = "db.internal.example"
_NEON_HOST = "ep-cool-darkness-123456.neon.tech"
_SECRET_URL = f"postgresql://ia_user:{_SECRET}@{_HOST}:5432/ia"
_PSYCOPG_URL = f"postgresql+psycopg://ia_user:{_SECRET}@{_NEON_HOST}/neondb?sslmode=require"
_QUERY_PASSWORD_URL = f"postgresql://ia_user@{_HOST}/ia?password={_SECRET}&sslmode=require"


class DatabaseConfigTests(unittest.TestCase):
    """URL rules and engine construction. These tests do not open a database connection."""

    def tearDown(self):
        reset_engine()

    def test_missing_database_url_fails_without_secrets(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaises(DatabaseConfigError) as raised:
                require_database_url()
        message = str(raised.exception)
        self.assertIn("DATABASE_URL", message)
        self.assertNotIn("password", message.lower())

    def test_database_url_follows_the_runtime_environment(self):
        first = "postgresql://ia_user:one@db-a.example/ia"
        second = "postgresql://ia_user:two@db-b.example/ia"
        with patch.dict(os.environ, {"DATABASE_URL": first}):
            self.assertEqual(database_url(), first)
            self.assertEqual(config_database_url(), first)
        with patch.dict(os.environ, {"DATABASE_URL": second}):
            self.assertEqual(database_url(), second)
            self.assertEqual(config_database_url(), second)

    def test_supported_postgresql_schemes_pass_validation(self):
        for url in (
            "postgresql://ia_user:pw@localhost/ia",
            "postgresql+psycopg://ia_user:pw@localhost/ia",
            "postgres://ia_user:pw@localhost/ia",
        ):
            with self.subTest(url=url):
                self.assertEqual(validate_database_url(url), url)

    def test_unsupported_scheme_hides_the_url(self):
        leaked = f"mysql://ia_user:{_SECRET}@{_HOST}/ia"
        with patch.dict(os.environ, {"DATABASE_URL": leaked}):
            with self.assertRaises(DatabaseConfigError) as raised:
                require_database_url()
        message = str(raised.exception)
        self.assertNotIn(_SECRET, message)
        self.assertNotIn(_HOST, message)
        self.assertNotIn("mysql://", message)
        self.assertIsNone(raised.exception.__cause__)

    def test_engine_uses_null_pool_and_pre_ping(self):
        created = {}

        def fake_create(url, **kwargs):
            created["url"] = url
            created["kwargs"] = kwargs
            return MagicMock()

        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            reset_engine()
            with patch("app.db.create_engine", side_effect=fake_create):
                get_engine()
        self.assertIs(created["kwargs"]["poolclass"], NullPool)
        self.assertTrue(created["kwargs"]["pool_pre_ping"])
        self.assertEqual(created["url"], _SECRET_URL)

    def test_concurrent_first_calls_create_one_engine(self):
        created = []

        def fake_create(url, **kwargs):
            created.append(url)
            return MagicMock()

        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            reset_engine()
            with patch("app.db.create_engine", side_effect=fake_create):
                threads = [threading.Thread(target=get_engine) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
        self.assertEqual(len(created), 1)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_failed_engine_creation_is_not_cached(self):
        calls = {"count": 0}

        def fake_create(url, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError(f"connect failed for {url}")
            return MagicMock()

        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            reset_engine()
            with patch("app.db.create_engine", side_effect=fake_create):
                with self.assertLogs("app.db", level="ERROR") as logs:
                    with self.assertRaises(DatabaseConnectionError) as raised:
                        get_engine()
                assert_hidden(self, raised.exception, logs.output, _SECRET_URL, _HOST)
                get_engine()
        self.assertEqual(calls["count"], 2)


class ConnectionSecrecyTests(unittest.TestCase):
    """Simulated driver failures. These tests do not open a database connection."""

    def tearDown(self):
        reset_engine()

    def test_engine_creation_hides_driver_url_formats(self):
        samples = (_SECRET_URL, _PSYCOPG_URL, _QUERY_PASSWORD_URL)
        for sample in samples:
            with self.subTest(sample=sample):
                reset_engine()
                with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
                    with patch("app.db.create_engine", side_effect=RuntimeError(sample)):
                        with self.assertLogs("app.db", level="ERROR") as logs:
                            with self.assertRaises(DatabaseConnectionError) as raised:
                                get_engine()
                assert_hidden(self, raised.exception, logs.output, sample, _HOST, _NEON_HOST)

    def test_connection_errors_hide_driver_url_formats(self):
        samples = (
            _SECRET_URL,
            _PSYCOPG_URL,
            _QUERY_PASSWORD_URL,
            f'could not translate host name "{_HOST}"',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                engine = MagicMock()
                engine.connect.side_effect = RuntimeError(sample)
                install_engine(engine)
                with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
                    with self.assertLogs("app.db", level="ERROR") as logs:
                        with self.assertRaises(DatabaseConnectionError) as raised:
                            check_database()
                assert_hidden(self, raised.exception, logs.output, sample, _HOST, _NEON_HOST)

    def test_open_connection_hides_driver_errors_for_migrations(self):
        engine = MagicMock()
        engine.connect.side_effect = OperationalError(_PSYCOPG_URL, {}, Exception(_SECRET))
        install_engine(engine)
        with patch.dict(os.environ, {"DATABASE_URL": _PSYCOPG_URL}):
            with self.assertLogs("app.db", level="ERROR") as logs:
                with self.assertRaises(DatabaseConnectionError) as raised:
                    open_connection()
        assert_hidden(self, raised.exception, logs.output, _PSYCOPG_URL, _SECRET, _NEON_HOST)

    def test_migration_connection_hides_errors_that_include_urls(self):
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value = connection
        install_engine(engine)
        with patch.dict(os.environ, {"DATABASE_URL": _PSYCOPG_URL}):
            with self.assertLogs("app.db", level="ERROR") as logs:
                with self.assertRaises(DatabaseConnectionError) as raised:
                    with migration_connection():
                        raise RuntimeError(f"online migration failed for {_PSYCOPG_URL}")
        assert_hidden(self, raised.exception, logs.output, _PSYCOPG_URL, _SECRET, _NEON_HOST)
        connection.close.assert_called_once()

    def test_migration_cleanup_does_not_hide_the_original_error(self):
        engine = MagicMock()
        connection = MagicMock()
        connection.close.side_effect = RuntimeError(f"close failed for {_SECRET_URL}")
        engine.connect.return_value = connection
        install_engine(engine)
        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            with self.assertRaises(RuntimeError) as raised:
                with migration_connection():
                    raise RuntimeError("revision failed")
        self.assertEqual(str(raised.exception), "revision failed")

    def test_library_logs_do_not_keep_connection_details(self):
        install_connection_log_filter()
        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            with self.assertLogs("sqlalchemy.engine", level="ERROR") as logs:
                logging.getLogger("sqlalchemy.engine").error(
                    "connection to %s failed password=%s",
                    _HOST,
                    _SECRET,
                )
        assert_hidden(self, None, logs.output, _SECRET, _HOST)

    def test_library_tracebacks_do_not_keep_connection_details(self):
        install_connection_log_filter()
        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            try:
                raise RuntimeError(_SECRET_URL)
            except RuntimeError:
                with self.assertLogs("sqlalchemy.engine", level="ERROR") as logs:
                    logging.getLogger("sqlalchemy.engine").error("driver failure", exc_info=True)
        assert_hidden(self, None, logs.output, _SECRET, _HOST, _SECRET_URL)

    def test_redact_database_text_strips_url_password_and_host(self):
        with patch.dict(os.environ, {"DATABASE_URL": _SECRET_URL}):
            leaked = f"connect {_PSYCOPG_URL} password={_SECRET} host {_HOST}"
            cleaned = redact_database_text(leaked)
        self.assertNotIn(_SECRET, cleaned)
        self.assertNotIn(_HOST, cleaned)
        self.assertNotIn(_NEON_HOST, cleaned)
        self.assertNotIn("postgresql+psycopg://", cleaned)


def assert_hidden(test, exc, logs, *samples):
    if exc is not None:
        test.assertIsNone(exc.__cause__)
        test.assertTrue(exc.__suppress_context__)
        test.assertEqual(str(exc), "Database connection failed")
    rendered = " ".join(logs)
    for sample in samples:
        test.assertNotIn(sample, rendered)
        if exc is not None:
            test.assertNotIn(sample, str(exc))


class SqliteSessionTests(unittest.TestCase):
    """SQLite-only session lifecycle. This does not verify PostgreSQL or Neon."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        install_engine(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE marks (id INTEGER PRIMARY KEY)"))

    def tearDown(self):
        reset_engine()

    def test_sqlite_connection_check_succeeds(self):
        self.assertTrue(check_database())

    def test_session_scope_commits_and_blocks_reuse(self):
        with session_scope() as session:
            session.execute(text("INSERT INTO marks (id) VALUES (1)"))
        self.assertEqual(self._count(), 1)
        with self.assertRaises(InvalidRequestError):
            session.execute(text("SELECT 1"))

    def test_session_scope_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with session_scope() as session:
                session.execute(text("INSERT INTO marks (id) VALUES (1)"))
                raise RuntimeError("request failed")
        self.assertEqual(self._count(), 0)
        with self.assertRaises(InvalidRequestError):
            session.execute(text("SELECT 1"))

    def test_request_teardown_rolls_back_without_committing(self):
        app = self._app()
        with app.app_context():
            session = get_request_session()
            session.execute(text("INSERT INTO marks (id) VALUES (1)"))
        self.assertEqual(self._count(), 0)
        with self.assertRaises(InvalidRequestError):
            session.execute(text("SELECT 1"))

    def test_request_transaction_commits_before_teardown(self):
        app = self._app()
        with app.app_context():
            with transaction(get_request_session()) as session:
                session.execute(text("INSERT INTO marks (id) VALUES (1)"))
        self.assertEqual(self._count(), 1)
        with self.assertRaises(InvalidRequestError):
            session.execute(text("SELECT 1"))

    def test_transaction_rolls_back_on_error(self):
        session = open_session()
        with self.assertRaises(RuntimeError):
            with transaction(session):
                session.execute(text("INSERT INTO marks (id) VALUES (1)"))
                raise RuntimeError("do not keep")
        self.assertEqual(self._count(), 0)
        session.close()

    def test_failed_commit_rolls_back_and_hides_credentials(self):
        session = open_session()
        leaked = RuntimeError(f"commit failed for {_PSYCOPG_URL}")
        with patch.dict(os.environ, {"DATABASE_URL": _PSYCOPG_URL}):
            with patch.object(session, "commit", side_effect=leaked):
                with self.assertLogs("app.db", level="ERROR") as logs:
                    with self.assertRaises(DatabaseConnectionError) as raised:
                        with transaction(session):
                            session.execute(text("INSERT INTO marks (id) VALUES (1)"))
        self.assertEqual(str(raised.exception), "Database connection failed")
        self.assertNotIn(_SECRET, " ".join(logs.output))
        self.assertNotIn(_NEON_HOST, " ".join(logs.output))
        self.assertEqual(self._count(), 0)
        session.close()

    def test_cleanup_error_does_not_hide_the_request_exception(self):
        app = self._app()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with self.assertRaises(RuntimeError) as raised:
                with app.app_context():
                    session = get_request_session()

                    def boom():
                        raise RuntimeError(f"rollback {_SECRET_URL}")

                    session.rollback = boom
                    raise RuntimeError("original request failed")
        finally:
            root.removeHandler(handler)
        self.assertEqual(str(raised.exception), "original request failed")
        rendered = " ".join(records)
        self.assertNotIn(_SECRET, rendered)
        self.assertNotIn(_HOST, rendered)

    def test_close_request_session_outside_context_is_a_no_op(self):
        close_request_session()

    def _app(self):
        app = Flask(__name__)
        init_app(app)
        return app

    def _count(self):
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT COUNT(*) FROM marks")).scalar()


if __name__ == "__main__":
    unittest.main()
