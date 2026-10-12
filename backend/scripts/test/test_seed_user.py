"""Unit checks for seed safety, idempotence, and data preservation."""

from unittest.mock import patch

from scripts import seed_user


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
    ):
        result = seed_user.seed_user()

    assert result["added_notes"] == 0
    add_note.assert_not_called()


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
    test_seed_user_refuses_production_environment()
    test_seed_user_requires_configured_long_password()
    print("Seed safety and idempotence checks passed.")
