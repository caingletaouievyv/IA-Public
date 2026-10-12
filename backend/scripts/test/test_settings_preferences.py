# IA/backend/scripts/test/test_settings_preferences.py

import tempfile
from unittest.mock import patch

from app.settings import manager


def test_context_source_preferences_persist_per_user_and_merge():
    with tempfile.TemporaryDirectory() as data_dir, patch.object(manager, "DATA_DIR", data_dir):
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


if __name__ == "__main__":
    test_context_source_preferences_persist_per_user_and_merge()
    print("Settings preference persistence checks passed.")
