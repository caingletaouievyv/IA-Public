# IA/backend/scripts/test/test_auth_repository.py
# SQLite account behavior. These tests do not prove PostgreSQL cross-process bootstrap safety.

import datetime
import os
import sys
import unittest
import uuid

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app import config
from app.auth import manager as auth_manager
from app.auth import repository
from app.auth.main_admin import MainAdminBootstrapError, bootstrap_main_admin
from app.auth.models import User
from app.auth.roles import ROLE_MAIN_ADMIN, ROLE_USER
from app.db import session_scope
from scripts.test.auth_db import close_sqlite_auth_database, install_sqlite_auth_database

INITIAL_PASSWORD = "initial-owner-password-8chars"


def _bootstrap_env(username: str) -> dict[str, str]:
    return {
        "MAIN_ADMIN_BOOTSTRAP_ENABLED": "true",
        "MAIN_ADMIN_BOOTSTRAP_USERNAME": username,
        "MAIN_ADMIN_BOOTSTRAP_SECRET": "x" * 8,
    }


class AuthRepositoryTests(unittest.TestCase):
    """SQLite-only. A passing run here is not a PostgreSQL or Neon concurrency check."""

    @classmethod
    def setUpClass(cls):
        cls.engine = install_sqlite_auth_database()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_sqlite_auth_database()

    def setUp(self):
        auth_manager._save_users([])

    def test_usernames_are_case_sensitive(self):
        first = auth_manager.create_user("Alice", "password-one")
        second = auth_manager.create_user("alice", "password-two")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first["user_id"], second["user_id"])
        duplicate = auth_manager.create_user("Alice", "other-password")
        self.assertIsNone(duplicate)
        response = self.client.post(
            "/auth/register",
            json={"username": "Alice", "password": "yet-another"},
        )
        self.assertEqual(response.status_code, 409)

    def test_password_hash_is_stored_and_verified_without_rehashing_imports(self):
        user_id = str(uuid.uuid4())
        stored_hash = "pbkdf2:sha256:600000$abc$def"
        auth_manager._save_users([{
            "user_id": user_id,
            "username": "kept",
            "password_hash": stored_hash,
            "role": ROLE_USER,
        }])
        loaded = auth_manager.find_user_by_id(user_id)
        self.assertEqual(loaded["user_id"], user_id)
        self.assertEqual(loaded["password_hash"], stored_hash)

        created = auth_manager.create_user("hashed", "plain-password")
        saved = auth_manager.find_user_by_username("hashed")
        self.assertNotEqual(saved["password_hash"], "plain-password")
        self.assertTrue(auth_manager.verify_password(saved, "plain-password"))
        self.assertFalse(auth_manager.verify_password(saved, "wrong-password"))
        self.assertEqual(saved["user_id"], created["user_id"])

    def test_login_jwt_has_no_role_claim(self):
        auth_manager.create_user("jwt-user", "jwt-password")
        response = self.client.post(
            "/auth/login",
            json={"username": "jwt-user", "password": "jwt-password"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertNotIn("password_hash", body)
        self.assertNotIn("role", body)
        payload = jwt.decode(body["token"], config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        self.assertEqual(payload["sub"], body["user_id"])
        self.assertNotIn("role", payload)
        self.assertEqual(
            self.client.post(
                "/auth/login",
                json={"username": "jwt-user", "password": "nope"},
            ).status_code,
            401,
        )

    def test_auth_me_reads_the_stored_role(self):
        user_id = str(uuid.uuid4())
        auth_manager._save_users([{
            "user_id": user_id,
            "username": "me-user",
            "password_hash": "hash-value",
            "role": ROLE_USER,
        }])
        token = jwt.encode(
            {"sub": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)},
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], ROLE_USER)
        self.assertNotIn("password_hash", response.get_json())

    def test_second_main_admin_insert_is_rejected(self):
        with session_scope() as session:
            repository.insert_user(
                session,
                user_id=str(uuid.uuid4()),
                username="owner",
                password_hash="hash-one",
                role=ROLE_MAIN_ADMIN,
            )
        with self.assertRaises(IntegrityError):
            with session_scope() as session:
                repository.insert_user(
                    session,
                    user_id=str(uuid.uuid4()),
                    username="other-owner",
                    password_hash="hash-two",
                    role=ROLE_MAIN_ADMIN,
                )
        self.assertEqual(len(auth_manager._load_users()), 1)

    def test_failed_bootstrap_rolls_back_the_marker_and_account(self):
        def fail_marker(session, user_id):
            raise RuntimeError("marker write failed")

        original = repository.insert_main_admin_marker
        repository.insert_main_admin_marker = fail_marker
        try:
            with self.assertRaises(RuntimeError):
                bootstrap_main_admin(
                    _bootstrap_env("owner"),
                    operator_secret="x" * 8,
                    operator_initial_password=INITIAL_PASSWORD,
                )
        finally:
            repository.insert_main_admin_marker = original
        self.assertEqual(auth_manager._load_users(), [])
        self.assertIsNone(auth_manager.find_user_by_username("owner"))

    def test_sqlite_schema_has_the_single_main_admin_index(self):
        with self.engine.connect() as connection:
            sql = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE name = 'users_one_main_admin'")
            ).scalar()
        self.assertIsNotNone(sql)
        self.assertIn("UNIQUE", sql.upper())
        self.assertIn(User.__tablename__, sql)


if __name__ == "__main__":
    unittest.main()
