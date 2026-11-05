# IA/backend/scripts/test/test_auth_postgres.py
# Live PostgreSQL checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable test database.
# These tests wipe auth tables. They refuse Neon hosts and never read DATABASE_URL as their target.

import os
import sys
import threading
import unittest

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app import create_app
from app import config
from app.auth import manager as auth_manager
from app.auth import repository
from app.auth.main_admin import (
    MainAdminBootstrapError,
    bootstrap_main_admin,
    load_marker,
    provision_initial_main_admin_account,
)
from app.auth.repository import AccountConflict, AccountStoreError
from app.auth.roles import ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER
from app.db import DatabaseConnectionError, install_engine, reset_engine
from scripts.test.pg_migrate import run_auth_migrations

_TEST_URL_ENV = "IA_TEST_DATABASE_URL"
_MIGRATION_DB = "ia_auth_migration"
_PASSWORD = "postgres-password-value"


def _disposable_postgres_url() -> str | None:
    url = (os.getenv(_TEST_URL_ENV) or "").strip()
    if not url:
        return None
    if url == (os.getenv("DATABASE_URL") or "").strip():
        raise RuntimeError("Refusing to use DATABASE_URL as the PostgreSQL test target.")
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    if "neon.tech" in host or "neon.tech" in url.lower():
        raise RuntimeError("Refusing to run auth tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


def _local_admin_url(url: str):
    parsed = make_url(url)
    if (parsed.host or "").lower() not in {"localhost", "127.0.0.1"}:
        return None
    return parsed.set(database="postgres")


class AlembicAuthMigrationTests(unittest.TestCase):
    """Apply the auth revision on a disposable local database. Not part of the default suite."""

    @classmethod
    def setUpClass(cls):
        url = _disposable_postgres_url()
        if url is None:
            raise unittest.SkipTest("IA_TEST_DATABASE_URL is not set")
        admin_url = _local_admin_url(url)
        if admin_url is None:
            raise unittest.SkipTest("Migration reset requires a local disposable PostgreSQL server.")
        cls.admin = create_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        with cls.admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS {_MIGRATION_DB} WITH (FORCE)'))
            connection.execute(text(f"CREATE DATABASE {_MIGRATION_DB}"))
        cls.engine = create_engine(
            admin_url.set(database=_MIGRATION_DB),
            poolclass=NullPool,
            pool_pre_ping=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS {_MIGRATION_DB} WITH (FORCE)'))
        cls.admin.dispose()

    def test_failed_upgrade_does_not_leave_a_stamped_revision(self):
        with self.engine.connect() as connection:
            with self.assertRaises(RuntimeError):
                run_auth_migrations(connection, fail_after_upgrade=True)
        with self.engine.connect() as connection:
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.users')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.notes')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.memories')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.settings')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_accounts')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_ledger')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_operations')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.activity_events')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.diagnostic_events')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.ask_pending_confirmations')")).scalar())
            self.assertIsNone(
                connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
            )

    def test_upgrade_downgrade_and_reupgrade(self):
        with self.engine.connect() as connection:
            run_auth_migrations(connection)
        self._assert_auth_catalog()
        with self.engine.connect() as connection:
            run_auth_migrations(connection, downgrade=True)
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.users')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.notes')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.memories')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.settings')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_accounts')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_ledger')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.credit_operations')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.activity_events')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.diagnostic_events')")).scalar())
            self.assertIsNone(connection.execute(text("SELECT to_regclass('public.ask_pending_confirmations')")).scalar())
            self.assertIsNone(
                connection.execute(text("SELECT to_regclass('public.main_admin_marker')")).scalar()
            )
            self.assertIsNone(
                connection.execute(text("SELECT to_regclass('public.demo_seed_marker')")).scalar()
            )
            run_auth_migrations(connection)
        self._assert_auth_catalog()

    def _assert_auth_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'users_one_main_admin'"
                )
            ).scalar()
            self.assertIsNotNone(index_sql)
            self.assertIn("UNIQUE", index_sql.upper())
            self.assertIn("main_admin", index_sql)
            constraints = {
                row[0]: row[1]
                for row in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.users'::regclass"
                    )
                )
            }
            self.assertIn("users_username_present", constraints)
            self.assertIn("users_password_hash_present", constraints)
            self.assertIn("users_role_known", constraints)
            self.assertIn("users_username_key", constraints)
            for table in ("main_admin_marker", "demo_seed_marker"):
                rows = connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        f"WHERE conrelid = 'public.{table}'::regclass"
                    )
                ).all()
                definitions = " ".join(definition for _name, definition in rows)
                self.assertIn("PRIMARY KEY", definitions)
                self.assertIn("singleton = 1", definitions)
                self.assertIn("UNIQUE", definitions)
                self.assertIn("user_id", definitions)
            fks = connection.execute(
                text(
                    "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) "
                    "FROM pg_constraint WHERE contype = 'f' "
                    "AND conrelid IN ('public.main_admin_marker'::regclass, "
                    "'public.demo_seed_marker'::regclass)"
                )
            ).all()
            self.assertEqual(len(fks), 2)
            for _table, definition in fks:
                self.assertIn("users", definition)
                self.assertIn("user_id", definition)
            connection.execute(
                text(
                    "INSERT INTO users (user_id, username, password_hash) "
                    "VALUES ('id-default', 'default-role', 'hash')"
                )
            )
            connection.commit()
            role = connection.execute(
                text("SELECT role FROM users WHERE user_id = 'id-default'")
            ).scalar()
            self.assertEqual(role, "user")
            with self.assertRaises(Exception):
                connection.execute(
                    text(
                        "INSERT INTO users (user_id, username, password_hash, role) "
                        "VALUES ('id-role', 'bad-role', 'hash', 'owner')"
                    )
                )
                connection.commit()
            connection.rollback()
            with self.assertRaises(Exception):
                connection.execute(
                    text(
                        "INSERT INTO users (user_id, username, password_hash, role) "
                        "VALUES ('id-main-1', 'main-one', 'hash', 'main_admin'), "
                        "('id-main-2', 'main-two', 'hash', 'main_admin')"
                    )
                )
                connection.commit()
            connection.rollback()
            connection.execute(text("DELETE FROM users"))
            connection.commit()


@unittest.skipUnless(os.getenv(_TEST_URL_ENV), "IA_TEST_DATABASE_URL is not set")
class PostgresAuthIntegrationTests(unittest.TestCase):
    """Requires a disposable PostgreSQL database. Not executed in the default suite."""

    @classmethod
    def setUpClass(cls):
        url = _disposable_postgres_url()
        if url is None:
            raise unittest.SkipTest("IA_TEST_DATABASE_URL is not set")
        cls.engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
        install_engine(cls.engine)
        with cls.engine.connect() as connection:
            run_auth_migrations(connection)
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()
        cls.users_stat = _file_stat(auth_manager.USERS_FILE)
        cls.marker_stat = _file_stat(
            os.path.join(auth_manager.DATA_DIR, ".ia_main_admin.json")
        )

    @classmethod
    def tearDownClass(cls):
        auth_manager._save_users([])
        reset_engine()
        cls.engine.dispose()

    def setUp(self):
        auth_manager._save_users([])

    def test_registration_case_login_and_roles(self):
        created = auth_manager.create_user("Alice", _PASSWORD)
        other = auth_manager.create_user("alice", "other-password-value")
        self.assertIsNotNone(created)
        self.assertIsNotNone(other)
        self.assertNotEqual(created["user_id"], other["user_id"])
        self.assertIsNone(auth_manager.create_user("Alice", "third-password"))
        stored = auth_manager.find_user_by_username("Alice")
        self.assertTrue(auth_manager.verify_password(stored, _PASSWORD))
        self.assertFalse(auth_manager.verify_password(stored, "other-password-value"))
        self.assertNotIn(_PASSWORD, stored["password_hash"])

        duplicate = self.client.post(
            "/auth/register",
            json={"username": "Alice", "password": "yet-another-password"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn("password_hash", duplicate.get_data(as_text=True))
        self.assertNotIn(_PASSWORD, duplicate.get_data(as_text=True))

        login = self.client.post(
            "/auth/login",
            json={"username": "Alice", "password": _PASSWORD},
        )
        self.assertEqual(login.status_code, 200)
        token = login.get_json()["token"]
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        self.assertEqual(set(claims), {"sub", "exp"})
        self.assertEqual(claims["sub"], created["user_id"])
        bad_login = self.client.post(
            "/auth/login",
            json={"username": "Alice", "password": "wrong-password"},
        )
        self.assertEqual(bad_login.status_code, 401)
        self.assertEqual(bad_login.get_json()["error"], "Invalid username or password")

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["role"], ROLE_USER)
        self.assertNotIn("password_hash", me.get_json())

        auth_manager._save_users([])
        provision_initial_main_admin_account("owner", "owner-password-value")
        member = auth_manager.create_user("member", "member-password-value")
        member_id = member["user_id"]
        owner_id = auth_manager.find_user_by_username("owner")["user_id"]
        denied = self.client.post(
            f"/admin/users/{member_id}/promote",
            headers=_bearer(member_id),
        )
        self.assertEqual(denied.status_code, 403)
        promoted = self.client.post(
            f"/admin/users/{member_id}/promote",
            headers=_bearer(owner_id),
        )
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.get_json()["role"], ROLE_ADMIN)
        self.assertNotIn("password_hash", promoted.get_data(as_text=True))
        demoted = self.client.post(
            f"/admin/users/{member_id}/demote",
            headers=_bearer(owner_id),
        )
        self.assertEqual(demoted.status_code, 200)
        self.assertEqual(auth_manager.get_user_role(member_id), ROLE_USER)
        with self.assertRaises(ValueError):
            auth_manager.set_user_role(member_id, ROLE_MAIN_ADMIN)
        self.assertEqual(auth_manager.get_user_role(member_id), ROLE_USER)

    def test_bootstrap_marker_and_rollback(self):
        message = provision_initial_main_admin_account("owner", "owner-password-value")
        self.assertIn("created", message)
        marker = load_marker()
        user = auth_manager.find_user_by_username("owner")
        self.assertEqual(marker["user_id"], user["user_id"])
        self.assertEqual(marker["username"], "owner")
        self.assertEqual(user["role"], ROLE_MAIN_ADMIN)
        again = provision_initial_main_admin_account("owner", "owner-password-value")
        self.assertIn("already designated", again)
        with self.assertRaises(MainAdminBootstrapError) as caught:
            provision_initial_main_admin_account("second", "second-password-value")
        self.assertNotIn("second-password-value", str(caught.exception))
        self.assertNotIn("://", str(caught.exception))
        self.assertEqual(len(auth_manager._load_users()), 1)

        auth_manager._save_users([])
        original = repository.insert_main_admin_marker

        def fail_marker(_session, _user_id):
            raise RuntimeError("marker write failed")

        repository.insert_main_admin_marker = fail_marker
        try:
            with self.assertRaises(RuntimeError):
                bootstrap_main_admin(
                    {
                        "MAIN_ADMIN_BOOTSTRAP_ENABLED": "true",
                        "MAIN_ADMIN_BOOTSTRAP_USERNAME": "owner",
                        "MAIN_ADMIN_BOOTSTRAP_SECRET": "x" * 8,
                    },
                    operator_secret="x" * 8,
                    operator_initial_password="initial-owner-password",
                )
        finally:
            repository.insert_main_admin_marker = original
        self.assertEqual(auth_manager._load_users(), [])
        self.assertIsNone(load_marker())

    def test_concurrent_bootstrap_uses_separate_connections(self):
        barrier = threading.Barrier(2)
        results: list[object] = []
        pids: list[int] = []
        original = repository.lock_user_table

        def locked(session):
            original(session)
            pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar())

        repository.lock_user_table = locked
        try:
            def worker():
                barrier.wait()
                try:
                    results.append(
                        provision_initial_main_admin_account("owner", "concurrent-owner-password")
                    )
                except BaseException as error:
                    results.append(error)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            repository.lock_user_table = original

        users = auth_manager._load_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["role"], ROLE_MAIN_ADMIN)
        self.assertEqual(len([item for item in results if isinstance(item, str)]), 2)
        self.assertEqual(len(set(pids)), 2)
        for item in results:
            self.assertNotIsInstance(item, BaseException)
            self.assertNotIn("concurrent-owner-password", str(item))

    def test_demo_seed_marker(self):
        import tempfile
        from unittest.mock import patch

        from scripts import seed_render_demo
        from app.credits import manager as credit_manager
        from app.notes import manager as notes_manager
        from app.settings import manager as settings_manager

        env = {
            "APP_ENV": "production",
            "RENDER_DEMO_SEED_ENABLED": "true",
            "SEED_USER_PASSWORD": "A-secure-demo-password-2026",
        }
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(notes_manager, "DATA_DIR", data_dir),
                patch.object(credit_manager, "DATA_DIR", data_dir),
                patch.object(settings_manager, "DATA_DIR", data_dir),
            ):
                created = seed_render_demo.seed_render_demo(env)
                self.assertTrue(created["created"])
                with repository.auth_session() as session:
                    marker_id = repository.demo_marker_user_id(session)
                self.assertEqual(marker_id, created["user_id"])
                stored_hash = auth_manager.find_user_by_username("demo")["password_hash"]
                auth_manager.set_user_role(created["user_id"], ROLE_ADMIN)
                again = seed_render_demo.seed_render_demo(env)
                self.assertFalse(again["created"])
                saved = auth_manager.find_user_by_username("demo")
                self.assertEqual(saved["password_hash"], stored_hash)
                self.assertEqual(saved["role"], ROLE_ADMIN)

                auth_manager._save_users([])
                auth_manager.create_user("demo", "existing-password-value")
                with self.assertRaises(RuntimeError) as caught:
                    seed_render_demo.seed_render_demo(env)
        self.assertIn("not verified", str(caught.exception))
        self.assertTrue(
            auth_manager.verify_password(
                auth_manager.find_user_by_username("demo"),
                "existing-password-value",
            )
        )

    def test_database_errors_do_not_expose_secrets(self):
        with repository.auth_session() as session:
            repository.insert_user(
                session,
                user_id="user-secret",
                username="secret-user",
                password_hash="pbkdf2:sha256:600000$secret-hash$abcdef",
                role=ROLE_USER,
            )
        with self.assertRaises(AccountConflict) as caught:
            with repository.auth_session() as session:
                repository.insert_user(
                    session,
                    user_id="user-secret-2",
                    username="secret-user",
                    password_hash="pbkdf2:sha256:600000$secret-hash$abcdef",
                    role=ROLE_USER,
                )
        self.assertEqual(str(caught.exception), "")
        self.assertNotIn("secret-hash", repr(caught.exception))
        self.assertNotIn("://", str(caught.exception))

        bad = create_engine(
            "postgresql+psycopg://ia_auth:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        previous = self.engine
        install_engine(bad)
        try:
            with self.assertRaises((AccountStoreError, DatabaseConnectionError)) as caught:
                auth_manager.store_is_empty()
        finally:
            install_engine(previous)
            bad.dispose()
        message = f"{caught.exception}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def test_json_account_files_are_not_touched(self):
        provision_initial_main_admin_account("owner", "owner-password-value")
        auth_manager.create_user("json-check", _PASSWORD)
        self.assertEqual(_file_stat(auth_manager.USERS_FILE), self.users_stat)
        self.assertEqual(
            _file_stat(os.path.join(auth_manager.DATA_DIR, ".ia_main_admin.json")),
            self.marker_stat,
        )


def _bearer(user_id: str) -> dict[str, str]:
    token = jwt.encode(
        {"sub": user_id, "exp": 9999999999},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )
    if isinstance(token, bytes):
        token = token.decode()
    return {"Authorization": f"Bearer {token}"}


def _file_stat(path: str):
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return (stat.st_size, stat.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
