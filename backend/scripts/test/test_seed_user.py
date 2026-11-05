"""Unit checks for seed safety, idempotence, and data preservation."""

import os
import tempfile
from unittest.mock import patch

from scripts import seed_user
from scripts.test.auth_db import close_sqlite_auth_database, install_sqlite_auth_database
from app.auth import manager as auth_manager
from app.credits import manager as credit_manager
from app.notes import manager as notes_manager
from app.settings import manager as settings_manager


def test_seed_user_adds_only_missing_notes_for_existing_user():
    existing_user = {"user_id": "existing-user", "username": seed_user.SEED_USERNAME}
    existing_note = {
        "title": seed_user.SEED_NOTES[0]["title"],
        "category": seed_user.SEED_NOTES[0]["category"],
        "content": "A version the user already customized.",
    }

    with (
        patch.object(seed_user, "APP_ENV", "development"),
        patch.object(seed_user, "SEED_PASSWORD", "test-seed-password-123"),
        patch.object(seed_user, "find_user_by_username", return_value=existing_user),
        patch.object(seed_user, "create_user") as create_user,
        patch.object(seed_user, "load_notes", return_value=[existing_note]),
        patch.object(seed_user, "add_note") as add_note,
        patch.object(seed_user, "get_credit_account"),
    ):
        result = seed_user.seed_user()

    create_user.assert_not_called()
    assert result["created"] is False
    assert result["added_notes"] == len(seed_user.SEED_NOTES) - 1
    assert add_note.call_count == len(seed_user.SEED_NOTES) - 1


def test_seed_user_second_run_adds_no_duplicates():
    existing_user = {"user_id": "existing-user", "username": seed_user.SEED_USERNAME}
    notes = [
        note | {"id": f"note-{index}"}
        for index, note in enumerate(seed_user.SEED_NOTES)
    ]

    with (
        patch.object(seed_user, "APP_ENV", "development"),
        patch.object(seed_user, "SEED_PASSWORD", "test-seed-password-123"),
        patch.object(seed_user, "find_user_by_username", return_value=existing_user),
        patch.object(seed_user, "load_notes", return_value=notes),
        patch.object(seed_user, "add_note") as add_note,
        patch.object(seed_user, "get_credit_account"),
    ):
        result = seed_user.seed_user()

    assert result["added_notes"] == 0
    add_note.assert_not_called()


def test_seed_user_preserves_existing_notes_settings_and_credit_balance():
    install_sqlite_auth_database()
    try:
        _assert_seed_preserves_existing_data()
    finally:
        close_sqlite_auth_database()


def _assert_seed_preserves_existing_data():
    with tempfile.TemporaryDirectory() as data_dir:
        with (
            patch.object(seed_user, "APP_ENV", "test"),
            patch.object(seed_user, "SEED_USERNAME", "demo-preservation-test"),
            patch.object(seed_user, "SEED_PASSWORD", "test-seed-password-123"),
            patch.object(notes_manager, "DATA_DIR", data_dir),
            patch.object(settings_manager, "DATA_DIR", data_dir),
            patch.object(credit_manager, "DATA_DIR", data_dir),
            patch.object(credit_manager, "AI_CREDIT_INITIAL_BALANCE", 23),
        ):
            user = auth_manager.create_user(seed_user.SEED_USERNAME, seed_user.SEED_PASSWORD)
            user_id = user["user_id"]
            custom_note = notes_manager.add_note(
                {
                    "title": seed_user.SEED_NOTES[0]["title"],
                    "category": seed_user.SEED_NOTES[0]["category"],
                    "content": "User-customized content",
                    "tags": ["custom"],
                },
                user_id,
            )
            settings_manager.save_settings(user_id, {"custom_preference": "preserve"})
            credit_manager.get_credit_account(user_id)
            credit_manager.reserve_credits(user_id, 4, "test_spend", "before-seed")

            note_before = notes_manager.get_note(custom_note["id"], user_id)
            settings_before = settings_manager.get_settings(user_id)
            credits_before = credit_manager.get_credit_account(user_id)

            first_result = seed_user.seed_user()
            seeded_notes = notes_manager.load_notes(user_id)
            second_result = seed_user.seed_user()

            assert first_result["created"] is False
            assert first_result["added_notes"] == len(seed_user.SEED_NOTES) - 1
            assert second_result["added_notes"] == 0
            assert notes_manager.get_note(custom_note["id"], user_id) == note_before
            assert len(notes_manager.load_notes(user_id)) == len(seeded_notes)
            assert settings_manager.get_settings(user_id) == settings_before
            assert credit_manager.get_credit_account(user_id) == credits_before


def test_seed_user_initializes_credit_for_new_demo_account():
    install_sqlite_auth_database()
    try:
        _assert_new_demo_credit_account()
    finally:
        close_sqlite_auth_database()


def _assert_new_demo_credit_account():
    with tempfile.TemporaryDirectory() as data_dir:
        with (
            patch.object(seed_user, "APP_ENV", "test"),
            patch.object(seed_user, "SEED_USERNAME", "demo-new-credit-test"),
            patch.object(seed_user, "SEED_PASSWORD", "test-seed-password-123"),
            patch.object(notes_manager, "DATA_DIR", data_dir),
            patch.object(credit_manager, "DATA_DIR", data_dir),
            patch.object(credit_manager, "AI_CREDIT_INITIAL_BALANCE", 67),
        ):
            result = seed_user.seed_user()
            account = credit_manager.get_credit_account(result["user_id"])

        assert result["created"] is True
        assert account["credit_balance"] == 67
        assert account["ledger"][0]["reason"] == "initial_balance"


def test_seed_user_refuses_production_environment():
    with (
        patch.object(seed_user, "APP_ENV", "production"),
        patch.object(seed_user, "SEED_PASSWORD", "test-seed-password-123"),
        patch.object(seed_user, "find_user_by_username") as find_user,
    ):
        try:
            seed_user.seed_user()
        except RuntimeError as error:
            assert "development" in str(error)
        else:
            raise AssertionError("Production seed should be refused")

    find_user.assert_not_called()


def test_seed_user_requires_configured_long_password():
    with (
        patch.object(seed_user, "APP_ENV", "development"),
        patch.object(seed_user, "SEED_PASSWORD", ""),
        patch.object(seed_user, "find_user_by_username") as find_user,
    ):
        try:
            seed_user.seed_user()
        except RuntimeError as error:
            assert "SEED_USER_PASSWORD" in str(error)
        else:
            raise AssertionError("Missing seed password should be refused")

    find_user.assert_not_called()


if __name__ == "__main__":
    test_seed_user_adds_only_missing_notes_for_existing_user()
    test_seed_user_second_run_adds_no_duplicates()
    test_seed_user_preserves_existing_notes_settings_and_credit_balance()
    test_seed_user_initializes_credit_for_new_demo_account()
    test_seed_user_refuses_production_environment()
    test_seed_user_requires_configured_long_password()
    print("Seed safety and idempotence checks passed.")
