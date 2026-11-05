# IA/backend/scripts/test/test_settings_repository.py
# Settings repository checks on SQLite. These do not open a PostgreSQL connection.

import datetime
import os
import sys
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt
from sqlalchemy import delete

from app import config, create_app
from app.auth.models import User
from app.db import DatabaseConnectionError, install_engine
from app.settings import manager
from app.settings.repository import SettingsStoreError
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class SettingsRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": "Bearer " + token}

    def test_missing_user_defaults_to_empty_document(self):
        self.assertEqual(manager.get_settings(self.user), {})
        loaded = self.client.get("/settings/", headers=self.headers(self.user))
        self.assertEqual(loaded.status_code, 200)
        self.assertIs(loaded.get_json()["memory_enabled"], False)
        self.assertIs(loaded.get_json()["ai_suggestions_enabled"], True)
        self.assertIs(loaded.get_json()["remember_command_enabled"], True)

    def test_merge_preserves_other_keys_and_value_types(self):
        manager.save_settings(self.user, {"theme": "dark", "limit": 3})
        saved = manager.save_settings(
            self.user,
            {
                "memory_enabled": True,
                "ask_context_sources": ["conversation", "notes"],
                "ask_context_modes": {"notes": "selected"},
            },
        )
        self.assertEqual(saved["theme"], "dark")
        self.assertEqual(saved["limit"], 3)
        self.assertIs(saved["memory_enabled"], True)
        self.assertEqual(saved["ask_context_sources"], ["conversation", "notes"])
        self.assertEqual(saved["ask_context_modes"], {"notes": "selected"})
        self.assertEqual(manager.get_settings(self.other), {})

    def test_api_update_shape_and_invalid_boolean(self):
        created = self.client.put(
            "/settings/",
            json={"theme": "dark"},
            headers=self.headers(self.user),
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.get_json(), {"theme": "dark"})
        updated = self.client.put(
            "/settings/",
            json={"memory_enabled": True, "show_context_source_labels": False},
            headers=self.headers(self.user),
        )
        body = updated.get_json()
        self.assertEqual(body["theme"], "dark")
        self.assertIs(body["memory_enabled"], True)
        self.assertIs(body["show_context_source_labels"], False)
        rejected = self.client.put(
            "/settings/",
            json={"memory_enabled": "true"},
            headers=self.headers(self.user),
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIs(manager.get_settings(self.user)["memory_enabled"], True)
        missing = self.client.put("/settings/", json=["theme"], headers=self.headers(self.user))
        self.assertEqual(missing.status_code, 400)

    def test_rollback_restores_the_previous_document(self):
        manager.save_settings(self.user, {"theme": "dark"})
        real_merge = manager.merge_settings

        def fail_after_merge(session, user_id, data):
            real_merge(session, user_id, data)
            raise RuntimeError("forced settings failure")

        with patch("app.settings.manager.merge_settings", fail_after_merge):
            with self.assertRaises(RuntimeError):
                manager.save_settings(self.user, {"limit": 4})
        self.assertEqual(manager.get_settings(self.user), {"theme": "dark"})

    def test_user_delete_removes_settings(self):
        manager.save_settings(self.user, {"theme": "dark"})
        from app.auth import repository as auth_repository

        with auth_repository.auth_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertEqual(manager.get_settings(self.user), {})

    def test_empty_user_is_rejected_and_files_stay_closed(self):
        with self.assertRaises(ValueError):
            manager.get_settings("")
        with patch("builtins.open", side_effect=AssertionError("settings opened a file")):
            manager.save_settings(self.user, {"theme": "dark"})
            self.assertEqual(manager.get_settings(self.user)["theme"], "dark")

    def test_database_errors_omit_connection_details(self):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        bad = create_engine(
            "postgresql+psycopg://settings:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((SettingsStoreError, DatabaseConnectionError)) as caught:
                manager.get_settings(self.user)
        finally:
            bad.dispose()
            close_notes_database()
            install_notes_database()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)
        self.assertIn(str(caught.exception), {"Could not access settings.", "Database connection failed"})


if __name__ == "__main__":
    unittest.main()
