"""AI diagnostics persistence, privacy, feedback, and admin review tests."""

import datetime
import json
import os
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt

from app import create_app, limiter
from app import config
from app.ai import routes as ai_routes
from app.ai.client import AIProviderError
from app.auth import manager as auth_manager
from app.auth.roles import ROLE_ADMIN
from app.common.understanding_gaps import report_understanding_gap, report_user_feedback
from app.credits import manager as credit_manager
from app.diagnostics import manager as diagnostics_manager
from app.memories import extraction


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.diagnostics_patch = patch.object(diagnostics_manager, "DATA_DIR", cls.temp_dir.name)
        cls.credits_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.auth_patch = patch.object(auth_manager, "DATA_DIR", cls.temp_dir.name)
        cls.users_patch = patch.object(
            auth_manager,
            "USERS_FILE",
            os.path.join(cls.temp_dir.name, "users.json"),
        )
        cls.diagnostics_patch.start()
        cls.credits_patch.start()
        cls.auth_patch.start()
        cls.users_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.users_patch.stop()
        cls.auth_patch.stop()
        cls.credits_patch.stop()
        cls.diagnostics_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def test_automatic_event_persists_without_sensitive_content(self):
        user_id = str(uuid.uuid4())
        sensitive_marker = "PRIVATE_PROMPT_SENTINEL"
        with self.assertLogs("ia.understanding", level="WARNING") as captured:
            report_understanding_gap(
                "memory.extraction.provider_failed",
                RuntimeError(sensitive_marker),
                user_id=user_id,
            )

        events = diagnostics_manager.list_events_for_user(user_id, limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "memory.extraction.provider_failed")
        self.assertEqual(events[0]["kind"], "automatic")
        stored = json.dumps(events[0])
        self.assertNotIn(sensitive_marker, stored)
        self.assertNotIn(sensitive_marker, "\n".join(captured.output))

    def test_feedback_requires_completed_operation_and_is_isolated(self):
        owner_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        operation_id = "ask-op-1"
        credit_manager.complete_operation(
            owner_id,
            operation_id,
            {"answer": "PRIVATE_ANSWER_SENTINEL", "memory_status": "disabled", "operation_id": operation_id},
        )

        response = self.client.post(
            "/diagnostics/feedback",
            json={"operation_id": operation_id, "feature": "ask", "reason": "wrong"},
            headers=self.headers(other_id),
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            "/diagnostics/feedback",
            json={"operation_id": operation_id, "feature": "ask", "reason": "wrong"},
            headers=self.headers(owner_id),
        )
        self.assertEqual(response.status_code, 201)
        events = diagnostics_manager.list_events_for_user(owner_id, limit=10)
        self.assertEqual(events[0]["kind"], "user_report")
        self.assertEqual(events[0]["feedback_reason"], "wrong")
        self.assertEqual(events[0]["operation_id"], operation_id)
        self.assertNotIn("PRIVATE_ANSWER_SENTINEL", json.dumps(events[0]))

        retry = self.client.post(
            "/diagnostics/feedback",
            json={"operation_id": operation_id, "feature": "ask", "reason": "other"},
            headers=self.headers(owner_id),
        )
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(len(diagnostics_manager.list_events_for_user(owner_id, limit=10)), 1)

    def test_admin_events_endpoint_requires_admin_role(self):
        event_user_id = str(uuid.uuid4())
        report_understanding_gap(
            "ask.operation_failed",
            RuntimeError("PRIVATE_ERROR_SENTINEL"),
            user_id=event_user_id,
        )

        denied_id = str(uuid.uuid4())
        auth_manager._save_users([{
            "user_id": denied_id,
            "username": "diag-user",
            "password_hash": "test-hash",
            "role": "user",
        }])
        denied = self.client.get("/diagnostics/events", headers=self.headers(denied_id))
        self.assertEqual(denied.status_code, 403)

        admin_id = str(uuid.uuid4())
        auth_manager._save_users([
            {
                "user_id": denied_id,
                "username": "diag-user",
                "password_hash": "test-hash",
                "role": "user",
            },
            {
                "user_id": admin_id,
                "username": "diag-admin",
                "password_hash": "test-hash",
                "role": ROLE_ADMIN,
            },
        ])
        allowed = self.client.get("/diagnostics/events", headers=self.headers(admin_id))
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.get_json()
        self.assertGreaterEqual(len(payload["events"]), 1)
        self.assertNotIn("PRIVATE_ERROR_SENTINEL", json.dumps(payload))

    def test_retention_cap_enforced(self):
        user_id = str(uuid.uuid4())
        with patch.object(diagnostics_manager, "DIAGNOSTICS_MAX_EVENTS_PER_USER", 2):
            for index in range(3):
                report_understanding_gap(
                    "memory.extraction.output_invalid",
                    ValueError(f"reject-{index}"),
                    user_id=user_id,
                )
        events = diagnostics_manager.list_events_for_user(user_id, limit=10)
        self.assertEqual(len(events), 2)

    def test_successful_ask_returns_operation_id(self):
        user_id = str(uuid.uuid4())
        operation_id = "ask-success-op"
        with patch.object(ai_routes, "ask", return_value=("answer text", 12, "disabled", None)):
            response = self.client.post(
                "/ai/ask",
                json={"question": "hello", "request_id": operation_id},
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["operation_id"], operation_id)
        self.assertTrue(credit_manager.has_completed_operation(user_id, operation_id))

    def test_successful_ask_does_not_persist_diagnostic(self):
        user_id = str(uuid.uuid4())
        with patch.object(ai_routes, "ask", return_value=("answer text", 12, "disabled", None)):
            response = self.client.post(
                "/ai/ask",
                json={"question": "hello", "request_id": "ask-no-diagnostic"},
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(diagnostics_manager.list_events_for_user(user_id, limit=10), [])

    def test_diagnostics_disabled_skips_persistence(self):
        user_id = str(uuid.uuid4())
        with patch.object(diagnostics_manager, "DIAGNOSTICS_ENABLED", False):
            report_understanding_gap(
                "memory.extraction.output_invalid",
                ValueError("reject"),
                user_id=user_id,
            )
            with self.assertRaises(ValueError):
                report_user_feedback(
                    user_id,
                    feature="ask",
                    reason="wrong",
                    operation_id="missing-op",
                )
        self.assertEqual(diagnostics_manager.list_events_for_user(user_id, limit=10), [])

    def test_memory_fallback_persists_expected_diagnostic_record(self):
        user_id = str(uuid.uuid4())
        with patch.object(extraction, "call_ai", side_effect=AIProviderError("groq request failed")):
            status = extraction.best_effort_extract(user_id, "Please remember that I prefer short answers.")
        self.assertEqual(status, "unavailable")
        events = diagnostics_manager.list_events_for_user(user_id, limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "memory.extraction.provider_failed")
        self.assertEqual(events[0]["category"], "provider_failure")

    def test_ask_provider_failure_records_provider_code(self):
        user_id = str(uuid.uuid4())
        operation_id = "ask-provider-failed"
        with patch.object(ai_routes, "ask", side_effect=AIProviderError("groq request failed")):
            response = self.client.post(
                "/ai/ask",
                json={"question": "hello", "request_id": operation_id},
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 502)
        events = diagnostics_manager.list_events_for_user(user_id, limit=10)
        self.assertEqual(events[0]["code"], "ask.provider_failed")

    def test_failed_ask_returns_generic_error_and_records_diagnostic(self):
        user_id = str(uuid.uuid4())
        operation_id = "ask-failed-op"
        with patch.object(ai_routes, "ask", side_effect=RuntimeError("PRIVATE_PROVIDER_FAILURE")):
            response = self.client.post(
                "/ai/ask",
                json={"question": "hello", "request_id": operation_id},
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "AI request failed")
        self.assertNotIn("PRIVATE_PROVIDER_FAILURE", response.get_data(as_text=True))
        events = diagnostics_manager.list_events_for_user(user_id, limit=10)
        self.assertEqual(events[0]["code"], "ask.operation_failed")


if __name__ == "__main__":
    unittest.main()
