# IA/backend/scripts/test/test_notes_repository.py
# Notes repository and API compatibility on SQLite. This does not verify PostgreSQL.

import datetime
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt
from sqlalchemy import create_engine, delete
from sqlalchemy.pool import NullPool

from app import config, create_app
from app.activity import manager as activity_manager
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine
from app.notes import manager as notes_manager
from app.notes.manager import (
    add_note,
    delete_note,
    get_categories,
    get_note,
    get_notes_list,
    get_tags,
    load_notes,
    save_notes,
    update_note,
)
from app.notes.repository import NoteStoreError, insert_note, notes_session
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database

_NOTE_KEYS = {"id", "title", "category", "content", "tags", "created_at", "updated_at"}


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


class NotesRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_create_read_update_delete_and_list(self):
        created = add_note(
            {"title": "Zebra", "category": "school", "content": "First", "tags": ["exam"]},
            self.user,
        )
        self.assertEqual(set(created), _NOTE_KEYS)
        self.assertTrue(created["created_at"].endswith("Z"))
        self.assertNotIn("+00:00", created["created_at"])
        self.assertEqual(get_note(created["id"], self.user), created)

        second = add_note(
            {"title": "Apple", "category": "home", "content": "", "tags": ["chore"]},
            self.user,
        )
        self.assertEqual([note["id"] for note in load_notes(self.user)], [created["id"], second["id"]])

        updated = update_note(created["id"], {"content": "Changed", "tags": ["exam", "lab"]}, self.user)
        self.assertEqual(updated["content"], "Changed")
        self.assertEqual(updated["title"], "Zebra")
        self.assertEqual(updated["created_at"], created["created_at"])
        self.assertTrue(updated["updated_at"].endswith("Z"))

        self.assertTrue(delete_note(second["id"], self.user))
        self.assertFalse(delete_note(second["id"], self.user))
        self.assertIsNone(get_note(second["id"], self.user))
        self.assertEqual([note["id"] for note in load_notes(self.user)], [created["id"]])

    def test_user_isolation(self):
        owned = add_note(
            {"title": "Private", "category": "school", "content": "Secret", "tags": ["mine"]},
            self.user,
        )
        add_note(
            {"title": "Other", "category": "school", "content": "Hidden", "tags": ["mine"]},
            self.other,
        )
        self.assertEqual([note["id"] for note in load_notes(self.user)], [owned["id"]])
        self.assertIsNone(get_note(owned["id"], self.other))
        self.assertIsNone(update_note(owned["id"], {"title": "Stolen"}, self.other))
        self.assertFalse(delete_note(owned["id"], self.other))
        self.assertEqual(get_note(owned["id"], self.user)["title"], "Private")

    def test_missing_and_invalid_ids(self):
        self.assertIsNone(get_note("missing-note", self.user))
        self.assertIsNone(update_note("missing-note", {"title": "Nope"}, self.user))
        self.assertFalse(delete_note("missing-note", self.user))

    def test_empty_title_does_not_persist_and_error_stays_generic(self):
        with self.assertRaises(NoteStoreError) as caught:
            add_note({"title": "", "category": "school", "content": "x", "tags": []}, self.user)
        self.assertEqual(str(caught.exception), "Could not access notes.")
        self.assertNotIn("school", repr(caught.exception))
        self.assertEqual(load_notes(self.user), [])

    def test_missing_owner_error_omits_the_user_id(self):
        missing = "user-secret-id"
        with self.assertRaises(NoteStoreError) as caught:
            add_note(
                {"title": "Orphan", "category": "school", "content": "x", "tags": []},
                missing,
            )
        self.assertNotIn(missing, f"{caught.exception} {caught.exception!r}")
        self.assertEqual(load_notes(missing), [])

    def test_transaction_rolls_back(self):
        with self.assertRaises(RuntimeError):
            with notes_session() as session:
                insert_note(
                    session,
                    self.user,
                    {"title": "Rollback", "category": "school", "content": "x", "tags": []},
                )
                raise RuntimeError("fail the write")
        self.assertEqual(load_notes(self.user), [])

    def test_filtering_limit_and_sorted_meta(self):
        add_note(
            {"title": "Later", "category": "beta", "content": "b", "tags": ["zoo", "lab"]},
            self.user,
        )
        first = add_note(
            {"title": "Sooner", "category": "alpha", "content": "a", "tags": ["lab"]},
            self.user,
        )
        add_note(
            {"title": "History", "category": "_history", "content": "[]", "tags": ["chat"]},
            self.user,
        )
        add_note(
            {"title": "Deck", "category": "_flashcards", "content": "{}", "tags": ["flashcards"]},
            self.user,
        )
        notes = load_notes(self.user)
        beta = notes[0]
        alpha = notes[1]
        self.assertEqual(beta["category"], "beta")
        self.assertEqual(alpha["id"], first["id"])

        school = get_notes_list(self.user, category="alpha", tag="lab")
        self.assertEqual([note["id"] for note in school], [alpha["id"]])
        self.assertEqual(get_notes_list(self.user, category="Alpha"), [])
        self.assertEqual(get_notes_list(self.user, tag="la"), [])
        self.assertEqual(
            [note["id"] for note in get_notes_list(self.user, tag="lab", limit=1)],
            [beta["id"]],
        )
        self.assertEqual(len(get_notes_list(self.user, limit=0)), 4)
        self.assertEqual(get_categories(self.user), ["alpha", "beta"])
        self.assertEqual(get_tags(self.user), ["chat", "flashcards", "lab", "zoo"])

    def test_save_notes_preserves_ids_and_order(self):
        original = add_note(
            {"title": "Kept", "category": "school", "content": "old", "tags": ["a"]},
            self.user,
        )
        original["content"] = "new"
        extra = {
            "id": str(uuid.uuid4()),
            "title": "Added",
            "category": "home",
            "content": "more",
            "tags": [],
            "created_at": original["created_at"],
            "updated_at": original["updated_at"],
        }
        save_notes([extra, original], self.user)
        stored = load_notes(self.user)
        self.assertEqual([note["id"] for note in stored], [extra["id"], original["id"]])
        self.assertEqual(stored[1]["content"], "new")
        self.assertEqual(stored[1]["created_at"], original["created_at"])

    def test_deleting_the_user_removes_notes(self):
        add_note(
            {"title": "Gone", "category": "school", "content": "x", "tags": []},
            self.user,
        )
        with notes_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(load_notes(self.user), [])

    def test_notes_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("notes opened a file")):
            created = add_note(
                {"title": "File", "category": "school", "content": "x", "tags": ["a"]},
                self.user,
            )
            self.assertEqual(get_note(created["id"], self.user)["content"], "x")
            save_notes([created], self.user)

    def test_connection_errors_omit_the_url(self):
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
            install_notes_database()
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)


class NotesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.activity_patch = patch.object(activity_manager, "DATA_DIR", cls.temp_dir.name)
        cls.activity_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.activity_patch.stop()
        close_notes_database()
        cls.temp_dir.cleanup()

    def test_api_round_trip_filters_and_ownership(self):
        owner = ensure_note_owner(str(uuid.uuid4()))
        other = ensure_note_owner(str(uuid.uuid4()))
        created = self.client.post(
            "/notes/",
            json={"title": "Zebra", "category": "school", "content": "Body", "tags": [" exam "]},
            headers=_headers(owner),
        )
        self.assertEqual(created.status_code, 201)
        note = created.get_json()
        self.assertEqual(set(note), _NOTE_KEYS)
        self.assertEqual(note["tags"], ["exam"])
        self.assertTrue(note["created_at"].endswith("Z"))

        empty = self.client.post(
            "/notes/",
            json={"title": "Empty", "category": "home", "content": "", "tags": []},
            headers=_headers(owner),
        )
        self.assertEqual(empty.status_code, 201)
        self.assertEqual(empty.get_json()["content"], "")

        fetched = self.client.get(f"/notes/{note['id']}", headers=_headers(owner))
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json(), note)

        hidden = self.client.get(f"/notes/{note['id']}", headers=_headers(other))
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.get_json()["error"], "Note not found")

        updated = self.client.put(
            f"/notes/{note['id']}",
            json={"content": "Changed"},
            headers=_headers(owner),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["content"], "Changed")
        self.assertEqual(updated.get_json()["title"], "Zebra")

        stolen = self.client.put(
            f"/notes/{note['id']}",
            json={"title": "Stolen"},
            headers=_headers(other),
        )
        self.assertEqual(stolen.status_code, 404)
        self.assertEqual(get_note(note["id"], owner)["title"], "Zebra")

        listed = self.client.get("/notes/?category=school&tag=exam&limit=1", headers=_headers(owner))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.get_json()], [note["id"]])
        other_list = self.client.get("/notes/", headers=_headers(other))
        self.assertEqual(other_list.get_json(), [])

        meta = self.client.get("/notes/meta", headers=_headers(owner))
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.get_json()["categories"], ["home", "school"])
        self.assertEqual(meta.get_json()["tags"], ["exam"])

        removed = self.client.delete(f"/notes/{note['id']}", headers=_headers(owner))
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.get_json(), {"message": "Note deleted"})
        self.assertEqual(self.client.get(f"/notes/{note['id']}", headers=_headers(owner)).status_code, 404)

    def test_invalid_input_and_missing_notes(self):
        owner = ensure_note_owner(str(uuid.uuid4()))
        headers = _headers(owner)
        missing_title = self.client.post(
            "/notes/",
            json={"category": "school", "content": "x", "tags": []},
            headers=headers,
        )
        self.assertEqual(missing_title.status_code, 400)
        long_title = self.client.post(
            "/notes/",
            json={"title": "x" * 101, "category": "school", "content": "x", "tags": []},
            headers=headers,
        )
        self.assertEqual(long_title.status_code, 400)
        empty_tag = self.client.post(
            "/notes/",
            json={"title": "Bad", "category": "school", "content": "x", "tags": [""]},
            headers=headers,
        )
        self.assertEqual(empty_tag.status_code, 400)
        empty_update = self.client.put("/notes/missing-note", json={"content": ""}, headers=headers)
        self.assertEqual(empty_update.status_code, 400)
        self.assertEqual(self.client.get("/notes/missing-note", headers=headers).status_code, 404)
        self.assertEqual(
            self.client.put("/notes/missing-note", json={"title": "Nope"}, headers=headers).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/notes/missing-note", headers=headers).status_code, 404)
        self.assertEqual(load_notes(owner), [])


if __name__ == "__main__":
    unittest.main()
