# IA/backend/scripts/test/test_memories_repository.py
# Memory repository behavior on SQLite. This does not verify PostgreSQL.

import os
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

from sqlalchemy import create_engine, delete
from sqlalchemy.pool import NullPool

from app.ai.engine import ask
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine
from app.memories import extraction, manager
from app.memories.repository import MemoryStoreError, memories_session
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class MemoryRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_create_update_dedup_replace_and_delete(self):
        created = manager.add_or_update_memories(
            self.user,
            [{"text": "The user lives in Paris.", "explicit_remember": True}],
        )
        self.assertEqual(created["added"], 1)
        self.assertEqual(len(manager.list_memories(self.user)), 1)
        again = manager.add_or_update_memories(
            self.user,
            [{"text": "  the   user lives in paris. ", "explicit_remember": True}],
        )
        self.assertEqual(again["added"], 0)
        self.assertEqual(len(manager.list_memories(self.user)), 1)

        first = manager.list_memories(self.user)[0]
        renamed = manager.add_or_update_memories(
            self.user,
            [{
                "text": "The user wants the assistant to be called Atlas.",
                "key": "assistant.name",
                "explicit_remember": True,
            }],
        )
        self.assertEqual(renamed["added"], 1)
        changed = manager.add_or_update_memories(
            self.user,
            [{
                "id": next(
                    item["id"] for item in manager.list_memories(self.user) if item.get("key") == "assistant.name"
                ),
                "text": "The user wants the assistant to be called Nova.",
                "key": "assistant.name",
                "explicit_remember": True,
            }],
        )
        self.assertEqual(changed["updated"], 1)
        names = [item for item in manager.list_memories(self.user) if item.get("key") == "assistant.name"]
        self.assertEqual(len(names), 1)
        self.assertEqual(names[0]["text"], "The user wants the assistant to be called Nova.")

        updated = manager.update_memory(self.user, first["id"], "The user lives in Lyon.")
        self.assertEqual(updated["text"], "The user lives in Lyon.")
        self.assertTrue(manager.delete_memory(self.user, first["id"]))
        self.assertFalse(manager.delete_memory(self.user, first["id"]))
        self.assertIsNone(manager.update_memory(self.user, "missing-memory", "The user lives in Lyon."))

    def test_saved_timestamps_round_trip(self):
        record = {
            "id": str(uuid.uuid4()),
            "text": "The user prefers tea.",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-06-01T00:00:00+00:00",
        }
        manager._save_memories(self.user, [record])
        stored = manager.load_memories(self.user)
        self.assertEqual(stored, [record])
        self.assertEqual(
            [item["id"] for item in manager.list_memories(self.user)],
            [record["id"]],
        )

    def test_user_isolation_and_list_order(self):
        older = {
            "id": str(uuid.uuid4()),
            "text": "The user lives in Paris.",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        newer = {
            "id": str(uuid.uuid4()),
            "text": "The user prefers tea.",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        manager._save_memories(self.user, [older, newer])
        manager._save_memories(
            self.other,
            [{
                "id": str(uuid.uuid4()),
                "text": "The user lives in Paris.",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }],
        )
        self.assertEqual(
            [item["id"] for item in manager.list_memories(self.user)],
            [newer["id"], older["id"]],
        )
        self.assertEqual(len(manager.list_memories(self.other)), 1)
        self.assertIsNone(manager.update_memory(self.other, older["id"], "The user lives in Rome."))
        self.assertFalse(manager.delete_memory(self.other, older["id"]))
        self.assertEqual(manager.load_memories(self.user)[0]["text"], older["text"])

    def test_invalid_input_is_not_stored(self):
        with self.assertRaises(ValueError):
            manager.update_memory(self.user, "missing", "")
        with self.assertRaises(ValueError):
            manager.validate_memory_text("x" * 501, explicit_remember=True)
        counts = manager.add_or_update_memories(
            self.user,
            [{"text": "", "explicit_remember": True}, {"text": "password=example-secret", "explicit_remember": True}],
        )
        self.assertEqual(counts, {"added": 0, "updated": 0, "removed": 0})
        self.assertEqual(manager.load_memories(self.user), [])

    def test_retrieval_ranks_overlap_and_keeps_the_latest_keyed_memory(self):
        manager._save_memories(
            self.user,
            [
                {
                    "id": "old-name",
                    "text": "The user wants the assistant to be called David.",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
                {
                    "id": "python",
                    "text": "The user prefers concise answers about Python.",
                    "created_at": "2024-02-01T00:00:00+00:00",
                    "updated_at": "2024-02-01T00:00:00+00:00",
                },
                {
                    "id": "new-name",
                    "text": "The user wants the assistant to be called Atlas.",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "updated_at": "2025-01-01T00:00:00+00:00",
                },
            ],
        )
        with patch("app.ai.client.call_ai", return_value='{"memory_key": null}'):
            ranked = manager.retrieve_memories(self.user, "How should you answer my Python question?")
        self.assertEqual([item["id"] for item in ranked], ["python"])
        with patch("app.ai.client.call_ai", return_value='{"memory_key": "assistant.name"}'):
            named = manager.retrieve_memories(self.user, "What is your name?")
        self.assertEqual([item["id"] for item in named], ["new-name"])

    def test_extraction_saves_a_durable_name_and_ask_injects_it(self):
        status = extraction.extract_and_save(self.user, "From now on, call yourself Atlas.")
        self.assertEqual(status, "saved")
        stored = manager.list_memories(self.user)
        self.assertEqual(stored[0]["key"], "assistant.name")
        self.assertIn("Atlas", stored[0]["text"])

        def _answer(prompt, question=None, messages=None):
            self.prompt = prompt
            return "Understood."

        with (
            patch("app.ai.engine.call_ai", side_effect=_answer),
            patch("app.ai.client.call_ai", return_value='{"memory_key": "assistant.name"}'),
            patch("app.memories.extraction.call_ai", return_value='{"upserts":[],"delete_ids":[]}'),
            patch("app.memory.manager.load_notes", return_value=[]),
        ):
            answer, _, memory_status, _ = ask(
                "What name did I give you?",
                user_id=self.user,
                memory_enabled=True,
                note_context_mode="off",
            )
        self.assertEqual(answer, "Understood.")
        self.assertEqual(memory_status, "unchanged")
        self.assertIn("Atlas", self.prompt)

    def test_transaction_rolls_back_and_user_delete_cascades(self):
        with self.assertRaises(RuntimeError):
            with memories_session() as session:
                from app.memories.repository import replace_memories

                replace_memories(
                    session,
                    self.user,
                    [{
                        "id": str(uuid.uuid4()),
                        "text": "The user likes rain.",
                        "created_at": "2024-01-01T00:00:00+00:00",
                        "updated_at": "2024-01-01T00:00:00+00:00",
                    }],
                )
                raise RuntimeError("fail the write")
        self.assertEqual(manager.load_memories(self.user), [])

        manager.add_or_update_memories(
            self.user,
            [{"text": "The user likes rain.", "explicit_remember": True}],
        )
        with memories_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(manager.load_memories(self.user), [])

    def test_memories_do_not_open_files_and_errors_omit_the_url(self):
        with patch("builtins.open", side_effect=AssertionError("memories opened a file")):
            manager.add_or_update_memories(
                self.user,
                [{"text": "The user likes rain.", "explicit_remember": True}],
            )
            self.assertEqual(len(manager.load_memories(self.user)), 1)

        bad = create_engine(
            "postgresql+psycopg://memories:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((MemoryStoreError, DatabaseConnectionError)) as caught:
                manager.load_memories(self.user)
        finally:
            install_notes_database()
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)


if __name__ == "__main__":
    unittest.main()
