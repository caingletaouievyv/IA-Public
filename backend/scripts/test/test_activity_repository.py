# IA/backend/scripts/test/test_activity_repository.py
# Activity repository checks on SQLite. These do not open a PostgreSQL connection.

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

from app.activity import manager
from app.activity import repository
from app.activity.models import ActivityEvent
from app.activity.repository import ActivityStoreError
from app.auth import repository as auth_repository
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class ActivityRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_create_list_order_and_user_isolation(self):
        first = manager.record_activity(self.user, "note.created")
        second = manager.record_activity(self.user, "note.updated")
        other = manager.record_activity(self.other, "note.deleted")
        events = manager.list_activity(self.user, 50)
        self.assertEqual([event["event_id"] for event in events], [second["event_id"], first["event_id"]])
        self.assertEqual(events[0]["description"], "Note updated")
        self.assertEqual(set(events[0]), {"event_id", "event_type", "description", "timestamp"})
        self.assertEqual(events[0]["timestamp"], second["timestamp"])
        self.assertEqual(manager.list_activity(self.other), [other])
        self.assertEqual(len(manager.list_activity(self.user, 1)), 1)

    def test_equal_timestamps_keep_later_inserts_first(self):
        moment = datetime.datetime(2026, 11, 4, 2, 0, tzinfo=datetime.timezone.utc)
        older = {
            "event_id": str(uuid.uuid4()),
            "event_type": "note.created",
            "description": "Note created",
            "timestamp": moment,
        }
        newer = {
            "event_id": str(uuid.uuid4()),
            "event_type": "note.updated",
            "description": "Note updated",
            "timestamp": moment,
        }
        with repository.activity_session() as session:
            repository.insert_event(session, self.user, older, manager.MAX_STORED_EVENTS)
        with repository.activity_session() as session:
            repository.insert_event(session, self.user, newer, manager.MAX_STORED_EVENTS)
        events = manager.list_activity(self.user, 10)
        self.assertEqual([event["event_id"] for event in events], [newer["event_id"], older["event_id"]])
        self.assertEqual(events[0]["timestamp"], events[1]["timestamp"])

    def test_limit_retention_and_invalid_input(self):
        with patch.object(manager, "MAX_STORED_EVENTS", 2):
            kept_first = manager.record_activity(self.user, "note.created")
            kept_second = manager.record_activity(self.user, "note.updated")
            dropped = manager.record_activity(self.user, "note.deleted")
        listed = manager.list_activity(self.user, 100)
        self.assertEqual(
            [event["event_id"] for event in listed],
            [dropped["event_id"], kept_second["event_id"]],
        )
        self.assertNotIn(kept_first["event_id"], [event["event_id"] for event in listed])
        self.assertEqual(len(manager.list_activity(self.user, 1000)), 2)
        with self.assertRaisesRegex(ValueError, "Unsupported activity event type"):
            manager.record_activity(self.user, "note.secret")
        with self.assertRaisesRegex(ValueError, "user_id required"):
            manager.record_activity("", "note.created")
        with self.assertRaisesRegex(ValueError, "positive integer"):
            manager.list_activity(self.user, True)
        self.assertEqual(self._count(self.user), 2)

    def test_rollback_drops_the_event_and_a_later_write_succeeds(self):
        real_insert = repository.insert_event

        def fail_after_insert(session, user_id, event, max_stored):
            real_insert(session, user_id, event, max_stored)
            raise RuntimeError("forced activity failure")

        with patch("app.activity.repository.insert_event", fail_after_insert):
            with self.assertRaisesRegex(RuntimeError, "forced activity failure"):
                manager.record_activity(self.user, "note.created")
        self.assertEqual(manager.list_activity(self.user), [])
        stored = manager.record_activity(self.user, "note.updated")
        self.assertEqual(manager.list_activity(self.user)[0]["event_id"], stored["event_id"])

    def test_user_delete_removes_events_and_files_stay_closed(self):
        manager.record_activity(self.user, "note.created")
        with auth_repository.auth_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(self._count(self.user), 0)
        with patch("builtins.open", side_effect=AssertionError("activity opened a file")):
            manager.record_activity(self.other, "note.created")
            self.assertEqual(len(manager.list_activity(self.other)), 1)

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://activity:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((ActivityStoreError, DatabaseConnectionError)) as caught:
                manager.list_activity(self.user)
        finally:
            bad.dispose()
            close_notes_database()
            install_notes_database()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)
        self.assertIn(str(caught.exception), {"Could not access activity.", "Database connection failed"})

    def _count(self, user_id: str) -> int:
        with repository.activity_session() as session:
            return session.scalar(
                select(func.count()).select_from(ActivityEvent).where(ActivityEvent.user_id == user_id)
            )


if __name__ == "__main__":
    unittest.main()
