"""Unit checks for the demo seed's idempotence and data preservation."""

from unittest.mock import patch

from scripts import seed_user


def test_seed_user_adds_only_missing_notes_for_existing_user():
    existing_user = {"user_id": "existing-user", "username": seed_user.SEED_USERNAME}
    existing_note = {
        "title": seed_user.SEED_NOTES[0]["title"],
        "category": seed_user.SEED_NOTES[0]["category"],
        "content": "A version the user already customized.",
    }

    with patch.object(seed_user, "find_user_by_username", return_value=existing_user), \
            patch.object(seed_user, "create_user") as create_user, \
            patch.object(seed_user, "load_notes", return_value=[existing_note]), \
            patch.object(seed_user, "add_note") as add_note:
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

    with patch.object(seed_user, "find_user_by_username", return_value=existing_user), \
            patch.object(seed_user, "load_notes", return_value=notes), \
            patch.object(seed_user, "add_note") as add_note:
        result = seed_user.seed_user()

    assert result["added_notes"] == 0
    add_note.assert_not_called()


if __name__ == "__main__":
    test_seed_user_adds_only_missing_notes_for_existing_user()
    test_seed_user_second_run_adds_no_duplicates()
    print("Seed idempotence checks passed.")