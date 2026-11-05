# IA/backend/scripts/test/test_notes_postgres.py
# Live PostgreSQL notes checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
# These tests refuse Neon hosts and never read DATABASE_URL as their target.

import datetime
import os
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app import config, create_app
from app.activity import manager as activity_manager
from app.auth import repository as auth_repository
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine, reset_engine
from app.notes.manager import add_note, delete_note, get_note, get_notes_list, load_notes, update_note
from app.notes.repository import NoteStoreError, insert_note, notes_session
from scripts.test.pg_migrate import run_auth_migrations

_TEST_URL_ENV = "IA_TEST_DATABASE_URL"
_NOTE_KEYS = {"id", "title", "category", "content", "tags", "created_at", "updated_at"}


def _disposable_postgres_url() -> str | None:
    url = (os.getenv(_TEST_URL_ENV) or "").strip()
    if not url:
        return None
    if url == (os.getenv("DATABASE_URL") or "").strip():
        raise RuntimeError("Refusing to use DATABASE_URL as the PostgreSQL test target.")
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    if "neon.tech" in host or "neon.tech" in url.lower():
        raise RuntimeError("Refusing to run notes tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


def _headers(user_id: str) -> dict:
    token = jwt.encode(
        {
            "sub": user_id,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
        },
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


class PostgresNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = _disposable_postgres_url()
        if url is None:
            raise unittest.SkipTest("IA_TEST_DATABASE_URL is not set")
        cls.engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
        install_engine(cls.engine)
        with cls.engine.connect() as connection:
            run_auth_migrations(connection)
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.activity_patch = patch.object(activity_manager, "DATA_DIR", cls.temp_dir.name)
        cls.activity_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.activity_patch.stop()
        cls.temp_dir.cleanup()
        reset_engine()
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM notes"))
        self.user = self._owner()
        self.other = self._owner()

    def _owner(self) -> str:
        user_id = str(uuid.uuid4())
        with auth_repository.auth_session() as session:
            auth_repository.insert_user(
                session,
                user_id=user_id,
                username=user_id,
                password_hash="test-hash",
                role="user",
            )
        return user_id

    def test_notes_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            tags = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'notes' AND column_name = 'tags'"
                )
            ).scalar()
            self.assertEqual(tags, "jsonb")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.notes'::regclass"
                    )
                )
            }
            self.assertIn("FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE", constraints["notes_user_id_fkey"])
            self.assertIn("PRIMARY KEY", constraints["notes_pkey"])
            self.assertIn("UNIQUE (user_id, seq)", constraints["notes_user_seq"])
            self.assertIn("length(title)", constraints["notes_title_present"])
            self.assertIn("length(category)", constraints["notes_category_present"])
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'notes_user_category'"
                )
            ).scalar()
            self.assertIn("(user_id, category)", index_sql)

    def test_crud_isolation_filter_and_api_shape(self):
        created = add_note(
            {"title": "Zebra", "category": "school", "content": "Body", "tags": ["exam"]},
            self.user,
        )
        self.assertEqual(set(created), _NOTE_KEYS)
        self.assertTrue(created["created_at"].endswith("Z"))
        later = add_note(
            {"title": "Apple", "category": "home", "content": "", "tags": ["chore"]},
            self.user,
        )
        self.assertEqual([note["id"] for note in load_notes(self.user)], [created["id"], later["id"]])
        updated = update_note(created["id"], {"content": "Changed"}, self.user)
        self.assertEqual(updated["content"], "Changed")
        self.assertEqual(updated["created_at"], created["created_at"])
        self.assertIsNone(get_note(created["id"], self.other))
        self.assertFalse(delete_note(created["id"], self.other))
        self.assertEqual(get_note(created["id"], self.user)["title"], "Zebra")
        self.assertEqual(
            [note["id"] for note in get_notes_list(self.user, category="school", tag="exam", limit=1)],
            [created["id"]],
        )
        self.assertEqual(get_notes_list(self.user, category="School"), [])

        response = self.client.post(
            "/notes/",
            json={"title": "Api", "category": "school", "content": "From API", "tags": [" exam "]},
            headers=_headers(self.user),
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(set(body), _NOTE_KEYS)
        self.assertEqual(body["tags"], ["exam"])
        self.assertEqual(self.client.get(f"/notes/{body['id']}", headers=_headers(self.other)).status_code, 404)
        listed = self.client.get("/notes/?category=school&tag=exam", headers=_headers(self.user))
        self.assertEqual(listed.status_code, 200)
        self.assertIn(body["id"], [item["id"] for item in listed.get_json()])
        missing = self.client.put("/notes/missing-note", json={"title": "Nope"}, headers=_headers(self.user))
        self.assertEqual(missing.status_code, 404)
        invalid = self.client.post("/notes/", json={"title": "", "category": "school"}, headers=_headers(self.user))
        self.assertEqual(invalid.status_code, 400)

    def test_transaction_rolls_back_and_user_delete_cascades(self):
        with self.assertRaises(RuntimeError):
            with notes_session() as session:
                insert_note(
                    session,
                    self.user,
                    {"title": "Rollback", "category": "school", "content": "x", "tags": []},
                )
                raise RuntimeError("fail the write")
        self.assertEqual(load_notes(self.user), [])

        add_note({"title": "Gone", "category": "school", "content": "x", "tags": []}, self.user)
        with notes_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(load_notes(self.user), [])

    def test_database_errors_omit_connection_details(self):
        with self.assertRaises(NoteStoreError) as caught:
            add_note({"title": "", "category": "school", "content": "x", "tags": []}, self.user)
        self.assertEqual(str(caught.exception), "Could not access notes.")
        self.assertNotIn("://", repr(caught.exception))

        bad = create_engine(
            "postgresql+psycopg://notes:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((NoteStoreError, DatabaseConnectionError)) as caught:
                load_notes(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def test_notes_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("notes opened a file")):
            created = add_note(
                {"title": "File", "category": "school", "content": "x", "tags": ["a"]},
                self.user,
            )
            self.assertEqual(get_note(created["id"], self.user)["title"], "File")


if __name__ == "__main__":
    unittest.main()
