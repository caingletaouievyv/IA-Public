# IA/backend/scripts/test/test_diagnostics_repository.py
# Diagnostics repository checks on SQLite. These do not open a PostgreSQL connection.

import datetime
import os
import sys
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.pool import NullPool

from app.auth import repository as auth_repository
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine
from app.diagnostics import manager
from app.diagnostics import repository
from app.diagnostics.models import DiagnosticEvent
from app.diagnostics.repository import DiagnosticsStoreError
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


def _event(user_id: str, *, kind: str = "automatic", operation_id: str | None = None, timestamp=None, **extra):
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": kind,
        "feature": "ask",
        "code": "ask.operation_failed",
        "category": "provider_failure",
        "fallback": "generic_error",
        "error_type": "RuntimeError",
        "user_key_prefix": manager.user_key_prefix(user_id),
    }
    if kind == "user_report":
        event["feedback_reason"] = "wrong"
        event["operation_id"] = operation_id or "op-1"
        event["code"] = "ask.feedback.reported"
        event["error_type"] = "none"
    event.update(extra)
    return event


class DiagnosticsRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_create_list_order_isolation_and_payload(self):
        moment = datetime.datetime(2026, 11, 4, 3, 0, tzinfo=datetime.timezone.utc)
        first = _event(self.user, timestamp=moment.isoformat(), provider="groq", memory_enabled=False)
        second = _event(
            self.user,
            timestamp=(moment + datetime.timedelta(seconds=1)).isoformat(),
            model="llama",
            memory_enabled=True,
        )
        other = _event(self.other, timestamp=(moment + datetime.timedelta(seconds=2)).isoformat())
        stored_first = manager.record_event(self.user, first)
        stored_second = manager.record_event(self.user, second)
        stored_other = manager.record_event(self.other, other)
        events = manager.list_events_for_user(self.user, 50)
        self.assertEqual(
            [event["event_id"] for event in events],
            [stored_second["event_id"], stored_first["event_id"]],
        )
        self.assertEqual(events[0]["memory_enabled"], True)
        self.assertEqual(events[0]["model"], "llama")
        self.assertNotIn("provider", events[0])
        self.assertEqual(events[1]["provider"], "groq")
        self.assertEqual(events[1]["memory_enabled"], False)
        self.assertEqual(manager.list_events_for_user(self.other), [stored_other])
        admin = manager.list_events_admin(limit=1)
        self.assertEqual(admin[0]["event_id"], stored_other["event_id"])
        self.assertNotIn("user_id", admin[0])

    def test_equal_timestamps_keep_later_inserts_first(self):
        moment = datetime.datetime(2026, 11, 4, 3, 5, tzinfo=datetime.timezone.utc).isoformat()
        older = _event(self.user, timestamp=moment)
        newer = _event(self.user, timestamp=moment)
        manager.record_event(self.user, older)
        manager.record_event(self.user, newer)
        events = manager.list_events_for_user(self.user, 10)
        self.assertEqual([event["event_id"] for event in events], [newer["event_id"], older["event_id"]])
        self.assertEqual(events[0]["timestamp"], events[1]["timestamp"])

    def test_duplicate_feedback_retention_limit_and_invalid_input(self):
        first = _event(self.user, kind="user_report", operation_id="same-op")
        second = _event(self.user, kind="user_report", operation_id="same-op", feedback_reason="other")
        stored = manager.record_event(self.user, first)
        again = manager.record_event(self.user, second)
        self.assertEqual(again["event_id"], stored["event_id"])
        self.assertEqual(self._count(self.user), 1)
        other_report = _event(self.other, kind="user_report", operation_id="same-op")
        manager.record_event(self.other, other_report)
        self.assertEqual(self._count(self.other), 1)

        with patch.object(manager, "DIAGNOSTICS_MAX_EVENTS_PER_USER", 2):
            kept_first = _event(self.user)
            kept_second = _event(self.user)
            dropped = _event(self.user)
            manager.record_event(self.user, kept_first)
            manager.record_event(self.user, kept_second)
            manager.record_event(self.user, dropped)
        listed = [event["event_id"] for event in manager.list_events_for_user(self.user, 100)]
        self.assertEqual(listed[:2], [dropped["event_id"], kept_second["event_id"]])
        self.assertNotIn(kept_first["event_id"], listed)

        aged = ensure_note_owner(str(uuid.uuid4()))
        old = _event(
            aged,
            timestamp=(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)).isoformat(),
        )
        with patch.object(manager, "DIAGNOSTICS_RETENTION_DAYS", 1):
            manager.record_event(aged, old)
            self.assertEqual(manager.list_events_for_user(aged, 10), [])
            fresh = _event(aged)
            manager.record_event(aged, fresh)
            self.assertEqual(
                [event["event_id"] for event in manager.list_events_for_user(aged, 10)],
                [fresh["event_id"]],
            )
            self.assertEqual(self._count(aged), 1)
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            manager.record_event(self.user, {**_event(self.user), "prompt": "secret"})
        with self.assertRaisesRegex(ValueError, "user_id required"):
            manager.record_event("", _event(self.user))
        with self.assertRaisesRegex(ValueError, "invalid"):
            broken = _event(self.user)
            broken["kind"] = "other"
            manager.record_event(self.user, broken)
        with self.assertRaisesRegex(ValueError, "timestamp is invalid"):
            stale = _event(self.user)
            stale["timestamp"] = "not-a-time"
            manager.record_event(self.user, stale)

    def test_rollback_user_delete_and_files_stay_closed(self):
        real_insert = repository.insert_event

        def fail_after_insert(session, user_id, event, max_stored, retention_days):
            real_insert(session, user_id, event, max_stored, retention_days)
            raise RuntimeError("forced diagnostics failure")

        with patch("app.diagnostics.repository.insert_event", fail_after_insert):
            with self.assertRaisesRegex(RuntimeError, "forced diagnostics failure"):
                manager.record_event(self.user, _event(self.user))
        self.assertEqual(manager.list_events_for_user(self.user), [])
        stored = manager.record_event(self.user, _event(self.user))
        self.assertEqual(manager.list_events_for_user(self.user)[0]["event_id"], stored["event_id"])
        with auth_repository.auth_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(self._count(self.user), 0)
        with patch("builtins.open", side_effect=AssertionError("diagnostics opened a file")):
            manager.record_event(self.other, _event(self.other))
            self.assertEqual(len(manager.list_events_for_user(self.other)), 1)

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://diagnostics:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((DiagnosticsStoreError, DatabaseConnectionError)) as caught:
                manager.list_events_for_user(self.user)
        finally:
            bad.dispose()
            close_notes_database()
            install_notes_database()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)
        self.assertIn(str(caught.exception), {"Could not access diagnostics.", "Database connection failed"})

    def _count(self, user_id: str) -> int:
        with repository.diagnostics_session() as session:
            return session.scalar(
                select(func.count()).select_from(DiagnosticEvent).where(DiagnosticEvent.user_id == user_id)
            )


if __name__ == "__main__":
    unittest.main()
