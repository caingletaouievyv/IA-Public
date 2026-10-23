# IA/backend/scripts/test/test_auto_seed_main_admin.py
# Development-only Main Admin auto-seed on create_app().

import os
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import config
from app import create_app
from app.auth import main_admin as main_admin_module
from app.auth import manager as auth_manager
from app.auth.main_admin import (
    AUTO_SEED_PASSWORD_ENV,
    PRODUCTION_BOOTSTRAP_PASSWORD_ENV,
    PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV,
    PRODUCTION_BOOTSTRAP_SECRET_ENV,
    MainAdminAutoSeedError,
    load_marker,
    maybe_auto_seed_main_admin_on_startup,
    maybe_production_bootstrap_main_admin_on_startup,
    maybe_provision_main_admin_on_startup,
)
from app.auth.roles import ROLE_MAIN_ADMIN, ROLE_USER


class AutoSeedMainAdminTests(unittest.TestCase):
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

    def auto_seed_patches(self, username="devowner", password="local-dev-password"):
        return patch.multiple(
            config,
            IA_AUTO_SEED_MAIN_ADMIN=True,
            APP_ENV="development",
            IA_AUTO_SEED_MAIN_ADMIN_USERNAME=username,
        ), patch.dict(os.environ, {AUTO_SEED_PASSWORD_ENV: password}, clear=False)

    def test_empty_store_seeds_on_create_app(self):
        cfg_patch, env_patch = self.auto_seed_patches()
        with cfg_patch, env_patch:
            create_app()
        user = auth_manager.find_user_by_username("devowner")
        self.assertIsNotNone(user)
        self.assertEqual(auth_manager.get_user_role(user["user_id"]), ROLE_MAIN_ADMIN)
        self.assertIsNotNone(load_marker(self.temp_dir.name))

    def test_repeat_startup_is_idempotent(self):
        cfg_patch, env_patch = self.auto_seed_patches()
        with cfg_patch, env_patch:
            create_app()
            create_app()
        self.assertEqual(len(auth_manager._load_users()), 1)

    def test_existing_users_are_not_modified(self):
        auth_manager._save_users([{
            "user_id": str(uuid.uuid4()),
            "username": "existing",
            "password_hash": "hash",
            "role": ROLE_USER,
        }])
        cfg_patch, env_patch = self.auto_seed_patches()
        with cfg_patch, env_patch:
            create_app()
        self.assertEqual(len(auth_manager._load_users()), 1)
        self.assertEqual(auth_manager.get_user_role(
            auth_manager.find_user_by_username("existing")["user_id"],
        ), ROLE_USER)
        self.assertIsNone(load_marker(self.temp_dir.name))

    def test_missing_credentials_refuses_startup(self):
        with patch.multiple(
            config,
            IA_AUTO_SEED_MAIN_ADMIN=True,
            APP_ENV="development",
            IA_AUTO_SEED_MAIN_ADMIN_USERNAME="",
        ):
            with self.assertRaises(MainAdminAutoSeedError):
                create_app()

    def test_production_environment_refuses_auto_seed(self):
        with patch.multiple(
            config,
            IA_AUTO_SEED_MAIN_ADMIN=True,
            APP_ENV="production",
            IA_AUTO_SEED_MAIN_ADMIN_USERNAME="devowner",
        ):
            with patch.dict(os.environ, {AUTO_SEED_PASSWORD_ENV: "local-dev-password"}, clear=False):
                with self.assertRaises(MainAdminAutoSeedError):
                    create_app()

    def production_bootstrap_env(self, username="prodowner", password="prod-pass", secret="prodsec12"):
        return patch.dict(
            os.environ,
            {
                PRODUCTION_BOOTSTRAP_PASSWORD_ENV: password,
                PRODUCTION_BOOTSTRAP_SECRET_ENV: secret,
                PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV: secret,
                "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_USERNAME": username,
            },
            clear=False,
        )

    def test_production_empty_store_bootstrap_on_startup(self):
        with patch.multiple(
            config,
            IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN=True,
            APP_ENV="production",
            IA_AUTO_SEED_MAIN_ADMIN=False,
        ):
            with self.production_bootstrap_env():
                create_app()
        user = auth_manager.find_user_by_username("prodowner")
        self.assertEqual(auth_manager.get_user_role(user["user_id"]), ROLE_MAIN_ADMIN)
        self.assertIsNotNone(load_marker(self.temp_dir.name))

    def test_production_skips_when_users_exist(self):
        auth_manager._save_users([{
            "user_id": str(uuid.uuid4()),
            "username": "existing",
            "password_hash": "hash",
            "role": ROLE_USER,
        }])
        with patch.multiple(
            config,
            IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN=True,
            APP_ENV="production",
            IA_AUTO_SEED_MAIN_ADMIN=False,
        ):
            with self.production_bootstrap_env():
                create_app()
        self.assertEqual(len(auth_manager._load_users()), 1)

    def test_production_bootstrap_requires_matching_secrets(self):
        with patch.multiple(
            config,
            IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN=True,
            APP_ENV="production",
            IA_AUTO_SEED_MAIN_ADMIN=False,
        ):
            with patch.dict(
                os.environ,
                {
                    PRODUCTION_BOOTSTRAP_PASSWORD_ENV: "prod-pass",
                    PRODUCTION_BOOTSTRAP_SECRET_ENV: "prodsec12",
                    PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV: "wrongsec",
                    "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_USERNAME": "prodowner",
                },
                clear=False,
            ):
                with self.assertRaises(MainAdminAutoSeedError) as ctx:
                    create_app()
        self.assertIn("confirmation failed", str(ctx.exception).lower())

    def test_concurrent_auto_seed_creates_single_account(self):
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def worker():
            barrier.wait()
            try:
                cfg_patch, env_patch = self.auto_seed_patches()
                with cfg_patch, env_patch:
                    maybe_auto_seed_main_admin_on_startup()
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors)
        self.assertEqual(len(auth_manager._load_users()), 1)
        self.assertEqual(len(main_admin_module.list_main_admin_user_ids()), 1)


if __name__ == "__main__":
    unittest.main()
