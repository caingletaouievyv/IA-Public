# IA/backend/scripts/test/test_settings_preferences.py

import datetime
import os
import tempfile
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import config, create_app
from app.settings import manager
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


def test_context_source_preferences_persist_per_user_and_merge():
    install_notes_database()
    try:
        _assert_context_preferences_merge()
    finally:
        close_notes_database()


def _assert_context_preferences_merge():
    with tempfile.TemporaryDirectory() as data_dir, patch.object(manager, "DATA_DIR", data_dir):
        ensure_note_owner("user-one")
        ensure_note_owner("user-two")
        manager.save_settings("user-one", {"theme": "dark"})
        saved = manager.save_settings(
            "user-one",
            {
                "ask_context_sources": ["conversation", "notes", "memory"],
                "ask_context_modes": {"notes": "selected", "memory": "automatic"},
            },
        )

        assert saved["theme"] == "dark"
        assert manager.get_settings("user-one")["ask_context_sources"] == [
            "conversation",
            "notes",
            "memory",
        ]
        assert manager.get_settings("user-one")["ask_context_modes"] == {
            "notes": "selected",
            "memory": "automatic",
        }
        assert manager.get_settings("user-two") == {}


def test_ai_suggestions_setting_defaults_on_and_persists_per_user():
    install_notes_database()
    try:
        _assert_ai_suggestions_default()
    finally:
        close_notes_database()


def _assert_ai_suggestions_default():
    with tempfile.TemporaryDirectory() as data_dir, patch.object(manager, "DATA_DIR", data_dir):
        app = create_app()
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        client = app.test_client()

        def headers(user_id):
            token = jwt.encode(
                {
                    "sub": user_id,
                    "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
                },
                config.JWT_SECRET,
                algorithm=config.JWT_ALGORITHM,
            )
            return {"Authorization": "Bearer " + token}

        first_user = ensure_note_owner(str(uuid.uuid4()))
        second_user = str(uuid.uuid4())
        self_user = headers(first_user)
        self_other = headers(second_user)

        assert client.get("/settings/", headers=self_user).get_json()["ai_suggestions_enabled"] is True
        assert client.put(
            "/settings/",
            json={"ai_suggestions_enabled": False},
            headers=self_user,
        ).get_json()["ai_suggestions_enabled"] is False
        assert client.get("/settings/", headers=self_user).get_json()["ai_suggestions_enabled"] is False
        assert client.get("/settings/", headers=self_other).get_json()["ai_suggestions_enabled"] is True
        assert client.put(
            "/settings/",
            json={"ai_suggestions_enabled": "false"},
            headers=self_user,
        ).status_code == 400


if __name__ == "__main__":
    test_context_source_preferences_persist_per_user_and_merge()
    test_ai_suggestions_setting_defaults_on_and_persists_per_user()
    print("Settings preference persistence checks passed.")
