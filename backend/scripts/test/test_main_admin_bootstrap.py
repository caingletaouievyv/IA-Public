# IA/backend/scripts/test/test_main_admin_bootstrap.py
# Main Admin bootstrap marker, idempotence, and conflict handling.

import os
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.auth import main_admin as main_admin_module
from app.auth import manager as auth_manager
from app import create_app
from app.auth.main_admin import (
    BOOTSTRAP_ENABLED_ENV,
    BOOTSTRAP_INITIAL_PASSWORD_ENV,
    BOOTSTRAP_SECRET_ENV,
    BOOTSTRAP_USERNAME_ENV,
    MainAdminBootstrapError,
    bootstrap_main_admin,
    load_marker,
)
from app.auth.roles import ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER


def bootstrap_env(username: str, secret: str = "x" * 8) -> dict[str, str]:
    return {
        BOOTSTRAP_ENABLED_ENV: "true",
        BOOTSTRAP_USERNAME_ENV: username,
        BOOTSTRAP_SECRET_ENV: secret,
    }


INITIAL_PASSWORD = "initial-owner-password-8chars"


def run_bootstrap(
    username: str,
    secret: str = "x" * 8,
    operator_secret: str | None = None,
    operator_initial_password: str | None = INITIAL_PASSWORD,
):
    configured = secret
    provided = configured if operator_secret is None else operator_secret
    return bootstrap_main_admin(
        bootstrap_env(username, configured),
        operator_secret=provided,
        operator_initial_password=operator_initial_password,
    )


class MainAdminBootstrapTests(unittest.TestCase):
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
        main_admin_module.marker_path(self.temp_dir.name).unlink(missing_ok=True)

    def seed_user(self, username: str, role=ROLE_USER):
        user_id = str(uuid.uuid4())
        users = auth_manager._load_users()
        users.append({
            "user_id": user_id,
            "username": username,
            "password_hash": "hash",
            "role": role,
        })
        auth_manager._save_users(users)
        return user_id

    def test_first_bootstrap_designates_main_admin(self):
        self.seed_user("owner")
        message = run_bootstrap("owner")
        self.assertIn("designated", message.lower())
        user = auth_manager.find_user_by_username("owner")
        self.assertEqual(auth_manager.get_user_role(user["user_id"]), ROLE_MAIN_ADMIN)
        marker = load_marker(self.temp_dir.name)
        self.assertEqual(marker["username"], "owner")
        self.assertEqual(marker["user_id"], user["user_id"])

    def test_repeat_bootstrap_is_idempotent(self):
        self.seed_user("owner")
        run_bootstrap("owner")
        message = run_bootstrap("owner")
        self.assertIn("already designated", message.lower())

    def test_repeat_with_different_username_is_rejected(self):
        self.seed_user("owner")
        self.seed_user("other")
        run_bootstrap("owner")
        with self.assertRaises(MainAdminBootstrapError):
            run_bootstrap("other")

    def test_empty_store_creates_main_admin_account(self):
        message = run_bootstrap("owner")
        self.assertIn("account created", message.lower())
        self.assertEqual(len(auth_manager._load_users()), 1)
        user = auth_manager.find_user_by_username("owner")
        self.assertEqual(auth_manager.get_user_role(user["user_id"]), ROLE_MAIN_ADMIN)
        marker = load_marker(self.temp_dir.name)
        self.assertEqual(marker["username"], "owner")

    def test_initial_credentials_authenticate(self):
        password = "login-check-password-8chars"
        run_bootstrap("owner", operator_initial_password=password)
        app = create_app()
        app.config.update(TESTING=True)
        client = app.test_client()
        response = client.post("/auth/login", json={"username": "owner", "password": password})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.get_json())

    def test_register_after_initial_creates_regular_user(self):
        run_bootstrap("owner")
        app = create_app()
        app.config.update(TESTING=True)
        client = app.test_client()
        response = client.post(
            "/auth/register",
            json={"username": "member", "password": "member-password-8"},
        )
        self.assertEqual(response.status_code, 201)
        member = auth_manager.find_user_by_username("member")
        self.assertEqual(auth_manager.get_user_role(member["user_id"]), ROLE_USER)

    def test_disabled_bootstrap_cannot_create_initial_account(self):
        with self.assertRaises(MainAdminBootstrapError):
            bootstrap_main_admin(
                {BOOTSTRAP_USERNAME_ENV: "owner", BOOTSTRAP_SECRET_ENV: "x" * 8},
                operator_secret="x" * 8,
                operator_initial_password=INITIAL_PASSWORD,
            )

    def test_empty_store_requires_initial_password(self):
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            run_bootstrap("owner", operator_initial_password=None)
        self.assertIn("password", str(ctx.exception).lower())

    def test_short_initial_password_is_accepted(self):
        message = run_bootstrap("owner", operator_initial_password="a")
        self.assertIn("account created", message.lower())
        user = auth_manager.find_user_by_username("owner")
        self.assertTrue(auth_manager.verify_password(user, "a"))
        self.assertEqual(auth_manager.get_user_role(user["user_id"]), ROLE_MAIN_ADMIN)

    def test_empty_initial_password_is_rejected(self):
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            run_bootstrap("owner", operator_initial_password="")
        self.assertIn("empty", str(ctx.exception).lower())
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            run_bootstrap("owner", operator_initial_password="   ")
        self.assertIn("password", str(ctx.exception).lower())

    def test_existing_users_are_not_replaced_when_username_missing(self):
        self.seed_user("existing")
        with self.assertRaises(MainAdminBootstrapError):
            run_bootstrap("missing-owner")
        self.assertEqual(len(auth_manager._load_users()), 1)
        self.assertIsNone(auth_manager.find_user_by_username("missing-owner"))

    def test_concurrent_empty_store_creates_single_account(self):
        barrier = threading.Barrier(2)
        results: list[str | BaseException] = []

        def worker():
            barrier.wait()
            try:
                results.append(run_bootstrap("owner"))
            except BaseException as error:
                results.append(error)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(auth_manager._load_users()), 1)
        self.assertEqual(len(main_admin_module.list_main_admin_user_ids()), 1)

    def test_missing_user_is_rejected_when_users_exist(self):
        self.seed_user("other")
        with self.assertRaises(MainAdminBootstrapError):
            run_bootstrap("missing-owner")

    def test_invalid_configuration_is_rejected(self):
        self.seed_user("owner")
        with self.assertRaises(MainAdminBootstrapError):
            bootstrap_main_admin({BOOTSTRAP_USERNAME_ENV: "owner"})
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            bootstrap_main_admin({
                BOOTSTRAP_ENABLED_ENV: "true",
                BOOTSTRAP_USERNAME_ENV: "owner",
                BOOTSTRAP_SECRET_ENV: "short",
            })
        self.assertIn("8", str(ctx.exception))

    def test_bootstrap_secret_eight_characters_is_accepted(self):
        self.seed_user("owner")
        secret = "12345678"
        message = bootstrap_main_admin(
            bootstrap_env("owner", secret),
            operator_secret=secret,
            operator_initial_password=None,
        )
        self.assertIn("designated", message.lower())

    def test_bootstrap_secret_shorter_than_eight_is_rejected(self):
        self.seed_user("owner")
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            bootstrap_main_admin(
                bootstrap_env("owner", "1234567"),
                operator_secret="1234567",
                operator_initial_password=None,
            )
        self.assertIn("8", str(ctx.exception))

    def test_demo_username_is_rejected(self):
        self.seed_user("demo")
        with self.assertRaises(MainAdminBootstrapError):
            run_bootstrap("demo")

    def test_existing_main_admin_without_marker_is_rejected(self):
        self.seed_user("owner", ROLE_MAIN_ADMIN)
        with self.assertRaises(MainAdminBootstrapError):
            run_bootstrap("owner")

    def test_existing_admin_is_promoted_only_via_explicit_bootstrap(self):
        user_id = self.seed_user("owner", ROLE_ADMIN)
        run_bootstrap("owner")
        self.assertEqual(auth_manager.get_user_role(user_id), ROLE_MAIN_ADMIN)

    def test_concurrent_bootstrap_creates_single_owner(self):
        self.seed_user("owner")
        barrier = threading.Barrier(2)
        results: list[str | BaseException] = []

        def worker():
            barrier.wait()
            try:
                results.append(run_bootstrap("owner"))
            except BaseException as error:
                results.append(error)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successes = [item for item in results if isinstance(item, str)]
        failures = [item for item in results if isinstance(item, MainAdminBootstrapError)]
        self.assertEqual(len(successes) + len(failures), 2)
        self.assertGreaterEqual(len(successes), 1)
        self.assertEqual(len(main_admin_module.list_main_admin_user_ids()), 1)
        marker = load_marker(self.temp_dir.name)
        self.assertEqual(marker["username"], "owner")

    def test_missing_operator_secret_is_rejected(self):
        self.seed_user("owner")
        secret = "cfgsec12"
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            bootstrap_main_admin(bootstrap_env("owner", secret), operator_secret=None)
        self.assertIn("confirmation", str(ctx.exception).lower())
        self.assertNotIn(secret, str(ctx.exception))

    def test_incorrect_operator_secret_is_rejected(self):
        self.seed_user("owner")
        secret = "cfgsec12"
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            bootstrap_main_admin(
                bootstrap_env("owner", secret),
                operator_secret="wrongsec",
            )
        self.assertIn("confirmation failed", str(ctx.exception).lower())
        self.assertNotIn(secret, str(ctx.exception))
        self.assertNotIn("wrongsec", str(ctx.exception))

    def test_correct_operator_secret_succeeds(self):
        self.seed_user("owner")
        secret = "matchsec"
        message = bootstrap_main_admin(
            bootstrap_env("owner", secret),
            operator_secret=secret,
            operator_initial_password=None,
        )
        self.assertIn("designated", message.lower())
        self.assertNotIn(secret, message)

    def test_configured_initial_password_requires_confirmation(self):
        secret = "x" * 8
        password = "configured-initial-password-8"
        env = bootstrap_env("owner", secret)
        env[BOOTSTRAP_INITIAL_PASSWORD_ENV] = password
        with self.assertRaises(MainAdminBootstrapError) as ctx:
            bootstrap_main_admin(env, operator_secret=secret, operator_initial_password="wrong-password-8chars")
        self.assertIn("password confirmation failed", str(ctx.exception).lower())
        self.assertNotIn(password, str(ctx.exception))

    def test_bootstrap_cli_refusal_never_echoes_secret(self):
        import sys
        from io import StringIO
        from scripts import bootstrap_main_admin as bootstrap_script

        self.seed_user("owner")
        secret = "cli-secret"
        env = bootstrap_env("owner", secret)
        captured = StringIO()

        with patch.dict(os.environ, env, clear=False):
            with patch("scripts.bootstrap_main_admin.getpass", return_value="wrongsec"):
                with patch("sys.stderr", captured):
                    try:
                        bootstrap_script.main()
                        self.fail("expected bootstrap refusal")
                    except MainAdminBootstrapError as error:
                        print(f"Main Admin bootstrap refused: {error}", file=sys.stderr)
        output = captured.getvalue()
        self.assertIn("refused", output.lower())
        self.assertNotIn(secret, output)
        self.assertNotIn("wrongsec", output)


if __name__ == "__main__":
    unittest.main()
