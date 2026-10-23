# IA/backend/scripts/test/test_auth_users_concurrency.py
# Process-local locking for users.json read-modify-write paths.

import os
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.auth import manager as auth_manager
from app.auth.roles import ROLE_ADMIN, ROLE_USER, normalize_role


class AuthUsersConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.data_dir_patch = patch.object(auth_manager, "DATA_DIR", cls.temp_dir.name)
        cls.users_file_patch = patch.object(
            auth_manager,
            "USERS_FILE",
            os.path.join(cls.temp_dir.name, "users.json"),
        )
        cls.data_dir_patch.start()
        cls.users_file_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.users_file_patch.stop()
        cls.data_dir_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        auth_manager._save_users([])

    def test_concurrent_registrations_preserve_distinct_users(self):
        barrier = threading.Barrier(6)
        results: list[dict | None] = []

        def worker(index: int):
            barrier.wait()
            results.append(auth_manager.create_user(f"member-{index}", "password-value"))

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        users = auth_manager._load_users()
        self.assertEqual(len(users), 6)
        self.assertEqual(len({user["username"] for user in users}), 6)
        self.assertEqual(len([item for item in results if item is not None]), 6)

    def test_concurrent_duplicate_username_registration_keeps_one_account(self):
        barrier = threading.Barrier(2)
        results: list[dict | None] = []

        def worker():
            barrier.wait()
            results.append(auth_manager.create_user("same-name", "password-value"))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        users = auth_manager._load_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "same-name")
        self.assertEqual(len([item for item in results if item is not None]), 1)

    def test_registration_concurrent_with_promotion_preserves_both_updates(self):
        promote_target_id = str(uuid.uuid4())
        auth_manager._save_users([{
            "user_id": promote_target_id,
            "username": "promote-me",
            "password_hash": "hash",
            "role": ROLE_USER,
        }])
        barrier = threading.Barrier(2)
        created: list[dict | None] = []
        promotion: list[dict] = []
        errors: list[BaseException] = []

        def register():
            barrier.wait()
            try:
                created.append(auth_manager.create_user("new-member", "password-value"))
            except BaseException as error:
                errors.append(error)

        def promote():
            barrier.wait()
            try:
                promotion.append(auth_manager.promote_user_to_admin(promote_target_id))
            except BaseException as error:
                errors.append(error)

        threads = [
            threading.Thread(target=register),
            threading.Thread(target=promote),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(created), 1)
        self.assertIsNotNone(created[0])
        self.assertEqual(len(promotion), 1)

        users = auth_manager._load_users()
        self.assertEqual(len(users), 2)
        roles = {
            user["user_id"]: normalize_role(user.get("role"))
            for user in users
        }
        self.assertEqual(roles[promote_target_id], ROLE_ADMIN)
        self.assertEqual(roles[created[0]["user_id"]], ROLE_USER)
        usernames = {user["username"] for user in users}
        self.assertEqual(usernames, {"promote-me", "new-member"})


if __name__ == "__main__":
    unittest.main()
