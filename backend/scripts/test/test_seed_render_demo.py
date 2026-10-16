"""Tests for explicitly enabled production demo seeding."""

import os
import tempfile
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts import seed_render_demo, seed_user
from app.auth import manager as auth_manager
from app.credits import manager as credit_manager
from app.notes import manager as notes_manager
from app.settings import manager as settings_manager


VALID_ENV = {
    "APP_ENV": "production",
    "RENDER_DEMO_SEED_ENABLED": "true",
    "SEED_USER_PASSWORD": "A-secure-demo-password-2026-unique!",
}


def _assert_configuration_refused(environ: dict[str, str], message: str) -> None:
    try:
        seed_render_demo.seed_render_demo(environ)
    except RuntimeError as error:
        assert message in str(error)
    else:
        raise AssertionError("Invalid production seed configuration was accepted")


def _patch_data_dirs(data_dir: str):
    return [
        patch.object(auth_manager, "DATA_DIR", data_dir),
        patch.object(auth_manager, "USERS_FILE", os.path.join(data_dir, "users.json")),
        patch.object(credit_manager, "DATA_DIR", data_dir),
        patch.object(notes_manager, "DATA_DIR", data_dir),
        patch.object(settings_manager, "DATA_DIR", data_dir),
    ]


def test_render_seed_rejects_non_production_environment():
    env = VALID_ENV | {"APP_ENV": "development"}
    _assert_configuration_refused(env, "APP_ENV=production")
    missing_environment = VALID_ENV.copy()
    missing_environment.pop("APP_ENV")
    _assert_configuration_refused(missing_environment, "APP_ENV=production")


def test_render_seed_requires_explicit_enable_flag():
    env = VALID_ENV | {"RENDER_DEMO_SEED_ENABLED": "false"}
    _assert_configuration_refused(env, "RENDER_DEMO_SEED_ENABLED=true")


def test_render_seed_rejects_missing_empty_or_short_password():
    missing_password = VALID_ENV.copy()
    missing_password.pop("SEED_USER_PASSWORD")
    _assert_configuration_refused(
        missing_password,
        "SEED_USER_PASSWORD",
    )
    _assert_configuration_refused(
        VALID_ENV | {"SEED_USER_PASSWORD": ""},
        "SEED_USER_PASSWORD",
    )
    _assert_configuration_refused(
        VALID_ENV | {"SEED_USER_PASSWORD": "a" * 11},
        "SEED_USER_PASSWORD",
    )


def test_render_seed_accepts_password_of_exactly_12_characters():
    password = "a" * 12
    env = VALID_ENV | {"SEED_USER_PASSWORD": password}

    assert seed_render_demo.validate_render_seed_configuration(env) == password


def test_render_seed_creates_user_and_sample_data_idempotently():
    with tempfile.TemporaryDirectory() as data_dir:
        output = StringIO()
        with ExitStack() as stack:
            for patcher in _patch_data_dirs(data_dir):
                stack.enter_context(patcher)
            with redirect_stdout(output), redirect_stderr(output):
                first = seed_render_demo.seed_render_demo(VALID_ENV)
                second = seed_render_demo.seed_render_demo(VALID_ENV)

            user = auth_manager.find_user_by_username("demo")
            notes = notes_manager.load_notes(user["user_id"])
            credits = credit_manager.get_credit_account(user["user_id"])

        assert first["created"] is True
        assert first["added_notes"] == len(seed_user.SEED_NOTES)
        assert second == {"user_id": first["user_id"], "created": False, "added_notes": 0}
        assert user["role"] == "user"
        assert auth_manager.verify_password(user, VALID_ENV["SEED_USER_PASSWORD"])
        assert len(notes) == len(seed_user.SEED_NOTES)
        assert {
            (note["title"], note["category"]) for note in notes
        } == {
            (note["title"], note["category"]) for note in seed_user.SEED_NOTES
        }
        assert credits["ledger"][0]["reason"] == "initial_balance"
        assert VALID_ENV["SEED_USER_PASSWORD"] not in output.getvalue()


def test_render_seed_refuses_preclaimed_demo_username_without_changing_data():
    with tempfile.TemporaryDirectory() as data_dir:
        with ExitStack() as stack:
            for patcher in _patch_data_dirs(data_dir):
                stack.enter_context(patcher)
            user = auth_manager.create_user("demo", "existing-password-value")
            user_id = user["user_id"]
            all_users = auth_manager._load_users()
            all_users[0]["role"] = "admin"
            auth_manager._save_users(all_users)
            settings_manager.save_settings(user_id, {"custom_preference": "keep"})
            credit_manager.get_credit_account(user_id)
            credit_manager.reserve_credits(user_id, 4, "test_spend", "before-seed")
            custom_note = notes_manager.add_note(
                {
                    "title": "My goals for this month",
                    "category": "Personal",
                    "content": "Customized sample note",
                    "tags": ["custom"],
                },
                user_id,
            )
            original_credits = credit_manager.get_credit_account(user_id)
            original_settings = settings_manager.get_settings(user_id)
            original_note = notes_manager.get_note(custom_note["id"], user_id)
            try:
                seed_render_demo.seed_render_demo(VALID_ENV)
            except RuntimeError as error:
                assert "not verified as created" in str(error)
            else:
                raise AssertionError("Seeder accepted a pre-existing demo account")

            stored_user = auth_manager.find_user_by_username("demo")
            saved_notes = notes_manager.load_notes(user_id)
            saved_credits = credit_manager.get_credit_account(user_id)
            saved_settings = settings_manager.get_settings(user_id)
            saved_custom_note = notes_manager.get_note(custom_note["id"], user_id)

        assert stored_user["role"] == "admin"
        assert auth_manager.verify_password(stored_user, "existing-password-value")
        assert not auth_manager.verify_password(stored_user, VALID_ENV["SEED_USER_PASSWORD"])
        assert saved_settings == original_settings
        assert saved_credits == original_credits
        assert saved_custom_note == original_note
        assert len(saved_notes) == 1
        assert not os.path.exists(os.path.join(data_dir, seed_render_demo.SEED_MARKER_FILENAME))


def test_render_seed_rerun_preserves_seeder_owned_account_data():
    with tempfile.TemporaryDirectory() as data_dir:
        with ExitStack() as stack:
            for patcher in _patch_data_dirs(data_dir):
                stack.enter_context(patcher)
            created = seed_render_demo.seed_render_demo(VALID_ENV)
            user_id = created["user_id"]
            users = auth_manager._load_users()
            users[0]["role"] = "admin"
            auth_manager._save_users(users)
            settings_manager.save_settings(user_id, {"custom_preference": "keep"})
            credit_manager.reserve_credits(user_id, 4, "test_spend", "before-rerun")
            first_note = notes_manager.load_notes(user_id)[0]
            notes_manager.update_note(
                first_note["id"],
                {"content": "Customized after initial seeding"},
                user_id,
            )
            original_password_hash = auth_manager.find_user_by_username("demo")["password_hash"]
            original_credits = credit_manager.get_credit_account(user_id)
            original_settings = settings_manager.get_settings(user_id)
            original_notes = notes_manager.load_notes(user_id)

            repeated = seed_render_demo.seed_render_demo(VALID_ENV)
            saved_user = auth_manager.find_user_by_username("demo")
            saved_credits = credit_manager.get_credit_account(user_id)
            saved_settings = settings_manager.get_settings(user_id)
            saved_notes = notes_manager.load_notes(user_id)

        assert repeated == {"user_id": user_id, "created": False, "added_notes": 0}
        assert saved_user["password_hash"] == original_password_hash
        assert saved_user["role"] == "admin"
        assert saved_credits == original_credits
        assert saved_settings == original_settings
        assert saved_notes == original_notes


if __name__ == "__main__":
    test_render_seed_rejects_non_production_environment()
    test_render_seed_requires_explicit_enable_flag()
    test_render_seed_rejects_missing_empty_or_short_password()
    test_render_seed_accepts_password_of_exactly_12_characters()
    test_render_seed_creates_user_and_sample_data_idempotently()
    test_render_seed_refuses_preclaimed_demo_username_without_changing_data()
    test_render_seed_rerun_preserves_seeder_owned_account_data()
    print("Render demo seed checks passed.")
