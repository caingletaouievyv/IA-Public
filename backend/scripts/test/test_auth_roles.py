# IA/backend/scripts/test/test_auth_roles.py
# Role helpers, /auth/me, diagnostics access, and unlimited-credit behavior.

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
from app.auth import manager as auth_manager
from app.auth.permissions import (
    can_assign_role,
    can_promote_users,
    can_view_diagnostics,
    has_unlimited_credits,
)
from app.auth.roles import ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER
from app.common.understanding_gaps import report_understanding_gap
from app.credits import manager as credit_manager
from app.diagnostics import manager as diagnostics_manager
from scripts.test.auth_db import close_sqlite_auth_database, install_sqlite_auth_database


class AuthRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        install_sqlite_auth_database()
        cls.diagnostics_patch = patch.object(diagnostics_manager, "DATA_DIR", cls.temp_dir.name)
        cls.credits_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.diagnostics_patch.start()
        cls.credits_patch.start()
        auth_manager._save_users([])
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.credits_patch.stop()
        cls.diagnostics_patch.stop()
        close_sqlite_auth_database()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()
        auth_manager._save_users([])

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

    def seed_user(self, user_id, username, role=ROLE_USER):
        auth_manager._save_users([{
            "user_id": user_id,
            "username": username,
            "password_hash": "test-hash",
            "role": role,
        }])

    def test_permission_helpers_for_three_roles(self):
        self.assertFalse(has_unlimited_credits(ROLE_USER))
        self.assertFalse(can_view_diagnostics(ROLE_USER))
        self.assertFalse(can_promote_users(ROLE_USER))

        self.assertTrue(has_unlimited_credits(ROLE_ADMIN))
        self.assertTrue(can_view_diagnostics(ROLE_ADMIN))
        self.assertFalse(can_promote_users(ROLE_ADMIN))

        self.assertTrue(has_unlimited_credits(ROLE_MAIN_ADMIN))
        self.assertTrue(can_view_diagnostics(ROLE_MAIN_ADMIN))
        self.assertTrue(can_promote_users(ROLE_MAIN_ADMIN))

        self.assertTrue(can_assign_role(ROLE_MAIN_ADMIN, ROLE_ADMIN))
        self.assertFalse(can_assign_role(ROLE_ADMIN, ROLE_ADMIN))
        self.assertFalse(can_assign_role(ROLE_MAIN_ADMIN, ROLE_MAIN_ADMIN))

    def test_auth_me_returns_role(self):
        user_id = str(uuid.uuid4())
        self.seed_user(user_id, "role-user", ROLE_USER)
        denied = self.client.get("/auth/me")
        self.assertEqual(denied.status_code, 401)

        response = self.client.get("/auth/me", headers=self.headers(user_id))
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["user_id"], user_id)
        self.assertEqual(payload["username"], "role-user")
        self.assertEqual(payload["role"], ROLE_USER)

    def test_diagnostics_events_allows_admin_and_main_admin(self):
        normal_id = str(uuid.uuid4())
        self.seed_user(normal_id, "normal", ROLE_USER)
        denied = self.client.get("/diagnostics/events", headers=self.headers(normal_id))
        self.assertEqual(denied.status_code, 403)

        for role in (ROLE_ADMIN, ROLE_MAIN_ADMIN):
            operator_id = str(uuid.uuid4())
            self.seed_user(operator_id, f"op-{role}", role)
            report_understanding_gap(
                "ask.operation_failed",
                RuntimeError("PRIVATE_ERROR_SENTINEL"),
                user_id=operator_id,
            )
            allowed = self.client.get("/diagnostics/events", headers=self.headers(operator_id))
            self.assertEqual(allowed.status_code, 200, role)
            payload = allowed.get_json()
            self.assertGreaterEqual(len(payload["events"]), 1)
            self.assertNotIn("PRIVATE_ERROR_SENTINEL", json.dumps(payload))

    def test_admin_roles_bypass_ask_credits(self):
        for role in (ROLE_ADMIN, ROLE_MAIN_ADMIN):
            user_id = str(uuid.uuid4())
            self.seed_user(user_id, f"credit-{role}", role)
            for index in range(config.AI_CREDIT_INITIAL_BALANCE):
                credit_manager.reserve_credits(
                    user_id,
                    config.AI_ASK_CREDIT_COST,
                    "ai_ask",
                    f"drain-{role}-{index}",
                )
            with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)):
                response = self.client.post(
                    "/ai/ask",
                    json={"question": "hello"},
                    headers={**self.headers(user_id), "Idempotency-Key": f"unlimited-{role}"},
                )
            self.assertEqual(response.status_code, 200, role)
            account = credit_manager.get_credit_account(user_id)
            self.assertEqual(account["credit_balance"], 0, role)
            self.assertFalse(
                any(entry.get("operation_id") == f"unlimited-{role}" for entry in account["ledger"]),
                role,
            )


if __name__ == "__main__":
    unittest.main()
