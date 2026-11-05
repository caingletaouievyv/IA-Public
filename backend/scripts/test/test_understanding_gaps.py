"""Privacy and formatting tests for content-free understanding-gap logs."""

import os
import unittest
from unittest.mock import patch

import requests
from app import config
from app.ai.client import AIProviderError, call_ai, call_single
from app.config import _bool_env
from app.common.understanding_gaps import report_understanding_gap
from app.notes import image_to_note
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class UnderstandingGapTests(unittest.TestCase):
    def test_logs_fixed_metadata_without_exception_content(self):
        sensitive_marker = "PRIVATE_USER_PROMPT_SENTINEL"
        with self.assertLogs("ia.understanding", level="WARNING") as captured:
            report_understanding_gap(
                "memory.extraction.provider_failed",
                RuntimeError(sensitive_marker),
            )

        message = "\n".join(captured.output)
        self.assertIn("understanding_gap", message)
        self.assertIn("feature=memory_extraction", message)
        self.assertIn("category=provider_failure", message)
        self.assertIn("fallback=continue_without_memory_update", message)
        self.assertIn("error_type=RuntimeError", message)
        self.assertNotIn(sensitive_marker, message)

    def test_rejects_unregistered_codes(self):
        with self.assertRaisesRegex(ValueError, "Unknown understanding-gap code"):
            report_understanding_gap("unknown.feature")

    def test_query_and_note_metadata_logging_is_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            for setting in ("INTENT_CACHE_LOG_HITS", "LOG_DROPPED_NOTES"):
                with self.subTest(setting=setting):
                    self.assertFalse(_bool_env(setting, False))
            self.assertTrue(_bool_env("EXPLICIT_DEBUG_OPT_IN", True))

        for setting in ("INTENT_CACHE_LOG_HITS", "LOG_DROPPED_NOTES"):
            if setting not in os.environ:
                with self.subTest(setting=setting):
                    self.assertFalse(getattr(config, setting))

    def test_provider_logging_omits_request_and_exception_text(self):
        sensitive_marker = "PRIVATE_PROVIDER_REQUEST_SENTINEL"
        with (
            self.assertLogs("app.ai.client", level="WARNING") as captured,
            patch(
                "app.ai.client.requests.post",
                side_effect=requests.ConnectionError(sensitive_marker),
            ),
        ):
            with self.assertRaisesRegex(AIProviderError, "request failed"):
                call_single(prompt=sensitive_marker, provider="groq")

        message = "\n".join(captured.output)
        self.assertIn("ai_provider_request_failed", message)
        self.assertIn("error_type=ConnectionError", message)
        self.assertNotIn(sensitive_marker, message)

    def test_unexpected_ai_error_log_omits_prompt_and_exception_text(self):
        sensitive_marker = "PRIVATE_AI_PROMPT_SENTINEL"
        with (
            self.assertLogs("app.ai.client", level="ERROR") as captured,
            patch("app.ai.client.call_single", side_effect=RuntimeError(sensitive_marker)),
        ):
            with self.assertRaisesRegex(RuntimeError, "AI request error"):
                call_ai(prompt=sensitive_marker)

        message = "\n".join(captured.output)
        self.assertIn("ai_client_unexpected_error", message)
        self.assertIn("error_type=RuntimeError", message)
        self.assertNotIn(sensitive_marker, message)

    def test_empty_image_summary_keeps_ocr_fallback_without_logging_content(self):
        sensitive_marker = "PRIVATE_OCR_CONTENT_SENTINEL"
        install_notes_database()
        ensure_note_owner("user-1")

        def capture_note(note, user_id):
            return note

        try:
            with (
                self.assertLogs("ia.understanding", level="WARNING") as captured,
                patch.object(image_to_note, "extract_text_from_images", return_value=sensitive_marker),
                patch.object(image_to_note, "summarize_for_note", return_value=""),
                patch.object(image_to_note, "find_note_by_title_category", return_value=None),
                patch.object(image_to_note, "add_note", side_effect=capture_note),
            ):
                note, appended = image_to_note.process_images_to_note(
                    [],
                    "Study",
                    "general",
                    user_id="user-1",
                )
            self.assertFalse(appended)
            self.assertEqual(note["content"], sensitive_marker)
            self.assertIn("code=notes.image_summary.empty", captured.output[0])
            self.assertNotIn(sensitive_marker, captured.output[0])
        finally:
            close_notes_database()


if __name__ == "__main__":
    unittest.main()
