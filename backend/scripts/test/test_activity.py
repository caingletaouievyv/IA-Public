"""Authenticated suggestion event and note-action tracking regressions."""

import datetime
import io
import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import create_app, config
from app.activity import manager as activity_manager
from app.notes import manager as notes_manager
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class ActivityRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.activity_data_patch = patch.object(activity_manager, "DATA_DIR", cls.temp_dir.name)
        cls.notes_data_patch = patch.object(notes_manager, "DATA_DIR", cls.temp_dir.name)
        cls.activity_data_patch.start()
        cls.notes_data_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.notes_data_patch.stop()
        cls.activity_data_patch.stop()
        close_notes_database()
        cls.temp_dir.cleanup()

    def user_id(self):
        return ensure_note_owner(str(uuid.uuid4()))

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def note_payload(self, category="study"):
        return {
            "title": "Private note title",
            "category": category,
            "content": "Private note content",
            "tags": [],
        }

    def test_note_create_update_delete_record_content_free_events(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        created = self.client.post("/notes/", json=self.note_payload(), headers=headers)
        self.assertEqual(created.status_code, 201)
        note_id = created.get_json()["id"]

        updated = self.client.put(
            f"/notes/{note_id}",
            json={"content": "Changed private content"},
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200)
        deleted = self.client.delete(f"/notes/{note_id}", headers=headers)
        self.assertEqual(deleted.status_code, 200)

        events = self.client.get("/activity/", headers=headers).get_json()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["note.deleted", "note.updated", "note.created"],
        )
        self.assertEqual(
            [event["description"] for event in events],
            ["Note deleted", "Note updated", "Note created"],
        )
        self.assertEqual(
            set(events[0]),
            {"event_id", "event_type", "description", "timestamp"},
        )
        serialized = str(events)
        self.assertNotIn("Private note title", serialized)
        self.assertNotIn("Private note content", serialized)
        self.assertNotIn("Changed private content", serialized)

    def test_flashcard_deck_events_are_distinct_and_history_is_excluded(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        for deck_category in ("flashcards", "_flashcards"):
            deck = self.client.post(
                "/notes/",
                json=self.note_payload(category=deck_category),
                headers=headers,
            )
            self.assertEqual(deck.status_code, 201)
            deck_id = deck.get_json()["id"]
            self.client.put(f"/notes/{deck_id}", json={"title": "Updated deck"}, headers=headers)
            self.client.delete(f"/notes/{deck_id}", headers=headers)

        history = self.client.post(
            "/notes/",
            json=self.note_payload(category="_history"),
            headers=headers,
        )
        history_id = history.get_json()["id"]
        self.client.put(f"/notes/{history_id}", json={"content": "[]"}, headers=headers)
        self.client.delete(f"/notes/{history_id}", headers=headers)

        events = self.client.get("/activity/", headers=headers).get_json()
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "flashcard_deck.deleted",
                "flashcard_deck.updated",
                "flashcard_deck.created",
                "flashcard_deck.deleted",
                "flashcard_deck.updated",
                "flashcard_deck.created",
            ],
        )

    def test_image_note_create_and_append_record_one_event_each(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        created_note = {"id": str(uuid.uuid4()), "category": "study"}
        updated_note = {"id": created_note["id"], "category": "study"}
        with patch(
            "app.notes.routes.process_images_to_note",
            side_effect=[(created_note, False), (updated_note, True)],
        ) as process_images:
            created = self.client.post(
                "/notes/from-images",
                data={"files": (io.BytesIO(b"image"), "study.png")},
                headers=headers,
                content_type="multipart/form-data",
            )
            appended = self.client.post(
                "/notes/from-images",
                data={"files": (io.BytesIO(b"image"), "study.png")},
                headers=headers,
                content_type="multipart/form-data",
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(appended.status_code, 201)
        self.assertEqual(process_images.call_count, 2)
        self.assertEqual(
            [event["event_type"] for event in self.client.get("/activity/", headers=headers).get_json()],
            ["note.updated", "note.created"],
        )

    def test_activity_requires_auth_and_isolated_by_user(self):
        user_id, other_user = self.user_id(), self.user_id()
        self.assertEqual(self.client.get("/activity/").status_code, 401)
        self.assertEqual(self.client.post("/notes/", json=self.note_payload()).status_code, 401)

        activity_manager.record_activity(user_id, "note.created")
        activity_manager.record_activity(user_id, "note.updated")
        activity_manager.record_activity(other_user, "note.deleted")

        own_events = self.client.get("/activity/", headers=self.headers(user_id)).get_json()
        other_events = self.client.get("/activity/", headers=self.headers(other_user)).get_json()
        self.assertEqual(len(own_events), 2)
        self.assertEqual(len(other_events), 1)
        self.assertEqual(other_events[0]["event_type"], "note.deleted")
        self.assertNotEqual(own_events[0]["event_id"], other_events[0]["event_id"])

    def test_recent_activity_is_newest_first_and_limit_is_bounded(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        for _ in range(activity_manager.MAX_ACTIVITY_LIMIT + 1):
            activity_manager.record_activity(user_id, "note.created")

        latest = self.client.get("/activity/?limit=1", headers=headers)
        bounded = self.client.get("/activity/?limit=10000", headers=headers)
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(len(latest.get_json()), 1)
        self.assertEqual(len(bounded.get_json()), activity_manager.MAX_ACTIVITY_LIMIT)
        self.assertEqual(
            bounded.get_json()[0]["event_id"],
            activity_manager.list_activity(user_id, 1)[0]["event_id"],
        )
        self.assertEqual(
            self.client.get("/activity/?limit=invalid", headers=headers).status_code,
            400,
        )
        self.assertEqual(self.client.get("/activity/?limit=0", headers=headers).status_code, 400)

    def test_concurrent_writes_keep_every_event(self):
        user_id = self.user_id()
        initial_event = activity_manager.record_activity(user_id, "note.created")

        with ThreadPoolExecutor(max_workers=12) as executor:
            events = list(
                executor.map(
                    lambda _: activity_manager.record_activity(user_id, "note.updated"),
                    range(60),
                )
            )

        stored_events = activity_manager.list_activity(user_id, 100)
        self.assertEqual(len(stored_events), 61)
        self.assertEqual(len({event["event_id"] for event in stored_events}), 61)
        self.assertEqual(
            {initial_event["event_id"], *(event["event_id"] for event in events)},
            {event["event_id"] for event in stored_events},
        )

    def test_note_mutation_remains_successful_when_activity_write_fails(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        with patch(
            "app.notes.routes.record_activity",
            side_effect=PermissionError("activity storage unavailable"),
        ):
            response = self.client.post(
                "/notes/",
                json=self.note_payload(),
                headers=headers,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/activity/", headers=headers).get_json(), [])

    def test_failed_note_operations_do_not_create_success_events(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        self.assertEqual(
            self.client.post(
                "/notes/",
                json={**self.note_payload(), "title": ""},
                headers=headers,
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.put("/notes/missing", json={"title": "Not found"}, headers=headers).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/notes/missing", headers=headers).status_code, 404)
        self.assertEqual(self.client.get("/activity/", headers=headers).get_json(), [])

        previous_propagation = self.app.config["PROPAGATE_EXCEPTIONS"]
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        try:
            with patch("app.notes.routes.add_note", side_effect=OSError("storage unavailable")):
                failed_write = self.client.post(
                    "/notes/",
                    json=self.note_payload(),
                    headers=headers,
                )
        finally:
            self.app.config["PROPAGATE_EXCEPTIONS"] = previous_propagation
        self.assertEqual(failed_write.status_code, 500)
        self.assertEqual(self.client.get("/activity/", headers=headers).get_json(), [])


if __name__ == "__main__":
    unittest.main()
