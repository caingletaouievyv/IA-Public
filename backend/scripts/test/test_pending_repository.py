# IA/backend/scripts/test/test_pending_repository.py
# Ask confirmation checks on SQLite. These do not open a PostgreSQL connection.

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
from app.notes import create_pending, delete_pending
from app.notes import pending_repository as repository
from app.notes.models import AskPendingConfirmation
from app.notes.pending_repository import PendingStoreError
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class PendingRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_create_and_delete_confirmations_are_isolated(self):
        created = create_pending.set_pending_create(
            self.user,
            need_title=False,
            need_content=True,
            title="Plan",
            category="school",
        )
        deleted = delete_pending.set_pending_delete(self.user, "note-1", "Plan")
        self.assertEqual(created["title"], "Plan")
        self.assertEqual(created["category"], "school")
        self.assertTrue(created["need_content"])
        self.assertFalse(created["need_title"])
        self.assertGreater(created["expires_at"], created["created_at"])
        self.assertEqual(delete_pending.get_pending_delete(self.user)["note_id"], "note-1")
        self.assertEqual(deleted["expected_title"], "Plan")
        self.assertIsNone(create_pending.get_pending_create(self.other))
        self.assertIsNone(delete_pending.get_pending_delete(self.other))
        self.assertEqual(self._count(self.user), 2)

    def test_replace_expiry_cancel_and_single_consume(self):
        create_pending.set_pending_create(self.user, need_title=True, need_content=True)
        replaced = create_pending.set_pending_create(
            self.user,
            need_title=False,
            need_content=True,
            title="Later",
        )
        self.assertEqual(create_pending.get_pending_create(self.user)["title"], "Later")
        self.assertEqual(self._count(self.user, repository.KIND_CREATE), 1)
        first = create_pending.consume_pending_create(self.user)
        second = create_pending.consume_pending_create(self.user)
        self.assertEqual(first["title"], replaced["title"])
        self.assertIsNone(second)
        delete_pending.set_pending_delete(self.user, "note-9", "Exact")
        self.assertIsNone(delete_pending.consume_pending_delete(self.user, match_title="exact"))
        self.assertIsNotNone(delete_pending.get_pending_delete(self.user))
        self.assertEqual(delete_pending.consume_pending_delete(self.user, match_title="Exact")["note_id"], "note-9")
        self.assertIsNone(delete_pending.consume_pending_delete(self.user))
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=create_pending.TTL_SECONDS + 5)
        create_pending.set_pending_create(self.other, need_title=True, need_content=False, title="Old")
        with patch("app.notes.pending_repository._now", return_value=future):
            self.assertIsNone(create_pending.get_pending_create(self.other))
        self.assertEqual(self._count(self.other), 0)
        with self.assertRaisesRegex(ValueError, "user_id"):
            create_pending.set_pending_create("", need_title=True, need_content=True)
        with self.assertRaisesRegex(ValueError, "expected_title"):
            delete_pending.set_pending_delete(self.user, "note-1", " ")

    def test_failed_consume_rolls_back_and_files_stay_closed(self):
        delete_pending.set_pending_delete(self.user, "note-1", "Keep")
        real_consume = repository.consume_pending

        def fail_after_consume(session, user_id, kind, match_title=None):
            real_consume(session, user_id, kind, match_title=match_title)
            raise RuntimeError("forced pending failure")

        with patch("app.notes.pending_repository.consume_pending", fail_after_consume):
            with self.assertRaisesRegex(RuntimeError, "forced pending failure"):
                delete_pending.consume_pending_delete(self.user)
        self.assertEqual(delete_pending.get_pending_delete(self.user)["note_id"], "note-1")
        with auth_repository.auth_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(self._count(self.user), 0)
        with patch("builtins.open", side_effect=AssertionError("pending confirmation opened a file")):
            create_pending.set_pending_create(self.other, need_title=True, need_content=True)
            self.assertIsNotNone(create_pending.get_pending_create(self.other))

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://pending:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((PendingStoreError, DatabaseConnectionError)) as caught:
                create_pending.get_pending_create(self.user)
        finally:
            bad.dispose()
            close_notes_database()
            install_notes_database()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def _count(self, user_id: str, kind: str | None = None) -> int:
        with repository.pending_session() as session:
            statement = select(func.count()).select_from(AskPendingConfirmation).where(
                AskPendingConfirmation.user_id == user_id
            )
            if kind is not None:
                statement = statement.where(AskPendingConfirmation.kind == kind)
            return session.scalar(statement)


if __name__ == "__main__":
    unittest.main()
