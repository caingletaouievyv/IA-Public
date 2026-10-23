# IA/backend/scripts/test/test_admin_users.py
# Main Admin user list and promotion APIs.

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
from app.auth import manager as auth_manager
from app.auth.roles import ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER


class AdminUserManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.auth_patch = patch.object(auth_manager, "DATA_DIR", cls.temp_dir.name)
        cls.users_patch = patch.object(
            auth_manager,
            "USERS_FILE",
            os.path.join(cls.temp_dir.name, "users.json"),
        )
        cls.auth_patch.start()
        cls.users_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.users_patch.stop()
        cls.auth_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()
        auth_manager._save_users([])

    def headers(self, user_id, *, accept="application/json"):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        out = {"Authorization": f"Bearer {token}"}
        if accept:
            out["Accept"] = accept
        return out

    def add_user(self, username, role=ROLE_USER):
        user_id = str(uuid.uuid4())
        users = auth_manager._load_users()
        users.append({
            "user_id": user_id,
            "username": username,
            "password_hash": "super-secret-hash-value",
            "role": role,
        })
        auth_manager._save_users(users)
        return user_id

    def test_main_admin_can_list_users_without_private_fields(self):
        main_admin_id = self.add_user("owner", ROLE_MAIN_ADMIN)
        self.add_user("member", ROLE_USER)
        response = self.client.get("/admin/users", headers=self.headers(main_admin_id))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.content_type)
        payload = response.get_json()
        self.assertEqual(len(payload["users"]), 2)
        encoded = json.dumps(payload)
        self.assertNotIn("password_hash", encoded)
        self.assertNotIn("super-secret-hash-value", encoded)
        roles = {item["username"]: item["role"] for item in payload["users"]}
        self.assertEqual(roles["owner"], ROLE_MAIN_ADMIN)
        self.assertEqual(roles["member"], ROLE_USER)

    def test_main_admin_can_promote_user_to_admin(self):
        main_admin_id = self.add_user("owner", ROLE_MAIN_ADMIN)
        member_id = self.add_user("member", ROLE_USER)
        response = self.client.post(
            f"/admin/users/{member_id}/promote",
            headers=self.headers(main_admin_id),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["role"], ROLE_ADMIN)
        self.assertEqual(auth_manager.get_user_role(member_id), ROLE_ADMIN)

    def test_admin_and_user_receive_forbidden(self):
        main_admin_id = self.add_user("owner", ROLE_MAIN_ADMIN)
        admin_id = self.add_user("operator", ROLE_ADMIN)
        user_id = self.add_user("member", ROLE_USER)
        target_id = self.add_user("promote-me", ROLE_USER)

        for actor_id in (admin_id, user_id):
            list_response = self.client.get("/admin/users", headers=self.headers(actor_id))
            self.assertEqual(list_response.status_code, 403, actor_id)
            promote_response = self.client.post(
                f"/admin/users/{target_id}/promote",
                headers=self.headers(actor_id),
            )
            self.assertEqual(promote_response.status_code, 403, actor_id)

        still_user = self.client.post(
            f"/admin/users/{target_id}/promote",
            headers=self.headers(main_admin_id),
        )
        self.assertEqual(still_user.status_code, 200)

    def test_promotion_rejects_admin_main_admin_and_missing_users(self):
        main_admin_id = self.add_user("owner", ROLE_MAIN_ADMIN)
        admin_id = self.add_user("operator", ROLE_ADMIN)
        main_id = self.add_user("main-copy", ROLE_MAIN_ADMIN)

        missing = self.client.post(
            f"/admin/users/{uuid.uuid4()}/promote",
            headers=self.headers(main_admin_id),
        )
        self.assertEqual(missing.status_code, 404)

        reject_admin = self.client.post(
            f"/admin/users/{admin_id}/promote",
            headers=self.headers(main_admin_id),
        )
        self.assertEqual(reject_admin.status_code, 400)

        reject_main = self.client.post(
            f"/admin/users/{main_id}/promote",
            headers=self.headers(main_admin_id),
        )
        self.assertEqual(reject_main.status_code, 400)
        self.assertEqual(auth_manager.get_user_role(main_id), ROLE_MAIN_ADMIN)

    def test_registration_still_creates_user_role(self):
        created = auth_manager.create_user("new-member", "test-password-value")
        self.assertIsNotNone(created)
        self.assertEqual(auth_manager.get_user_role(created["user_id"]), ROLE_USER)

    def test_admin_users_api_not_shadowed_by_spa_fallback(self):
        main_admin_id = self.add_user("owner", ROLE_MAIN_ADMIN)
        admin_id = self.add_user("operator", ROLE_ADMIN)
        user_id = self.add_user("member", ROLE_USER)

        for actor_id, expected_status in (
            (main_admin_id, 200),
            (admin_id, 403),
            (user_id, 403),
        ):
            response = self.client.get("/admin/users", headers=self.headers(actor_id))
            self.assertEqual(response.status_code, expected_status, actor_id)
            self.assertIn("application/json", response.content_type)
            payload = response.get_json()
            self.assertIsInstance(payload, dict, actor_id)
            if expected_status == 200:
                self.assertIn("users", payload)
            else:
                self.assertEqual(payload.get("error"), "Forbidden")

    def test_admin_users_browser_shell_without_auth(self):
        response = self.client.get("/admin/users", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn(b"html", response.data.lower())

    def test_admin_diagnostics_frontend_route_still_serves_html(self):
        response = self.client.get("/admin/diagnostics", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)


if __name__ == "__main__":
    unittest.main()
