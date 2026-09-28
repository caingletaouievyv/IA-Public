from app.memory.manager import build_context


def test_build_context_keeps_selected_notes_for_generic_queries(monkeypatch):
    note = {
        "id": "note-123",
        "title": "grocery list",
        "content": "milk, eggs, bread, fruit",
        "category": "shopping",
        "tags": ["kitchen"],
    }

    monkeypatch.setattr("app.memory.manager.load_notes", lambda user_id: [note])

    result = build_context("check the notes included", note_ids=["note-123"], user_id="user-1")

    assert result["context"], "explicitly selected notes should still be included even for generic queries"
    assert "grocery list" in result["context"]
