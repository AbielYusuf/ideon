"""Authentication, authorization, isolation, and legacy migration tests."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

import auth_service
import auth_store
import database

# Keep module import from touching the live database when this file runs alone.
_TEMPORARY = tempfile.TemporaryDirectory()
database.DATABASE_PATH = Path(_TEMPORARY.name) / "auth-tests.db"
database.initialize_database()

from main import app  # noqa: E402
from tests.support import (  # noqa: E402
    ANALYSIS,
    CRITERIA,
    TEST_PASSWORD,
    authenticated_user,
    create_user,
    fresh_database,
    insert_idea,
    login_client,
)

VALID_ANALYSIS = json.dumps(ANALYSIS.model_dump())
VALID_SCORING = json.dumps(
    {
        "criteria": [
            {
                **criterion,
                "weight": 20.0,
                "weighted_score": round(criterion["score"] * 0.2, 2),
            }
            for criterion in CRITERIA
        ]
    }
)


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.client = TestClient(app)

    def register(self, *, username="new-user", email=None, password=TEST_PASSWORD):
        return self.client.post(
            "/api/auth/register",
            json={
                "username": username,
                "email": email or f"{username}@example.com",
                "password": password,
                "confirm_password": password,
            },
        )


class RegistrationTests(AuthTestCase):
    def test_registration_creates_account_and_session(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["username"], "new-user")
        self.assertEqual(body["role"], "user")
        self.assertNotIn("password", body)
        self.assertNotIn("password_hash", body)
        self.assertIn("ideon_session", response.cookies)
        self.assertIn("ideon_csrf", response.cookies)

        profile = self.client.get("/api/auth/me")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["email"], "new-user@example.com")

    def test_registration_stores_only_argon2id_hash(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)

        user = auth_store.get_user_by_email("new-user@example.com")
        self.assertIsNotNone(user)
        self.assertNotEqual(user["password_hash"], TEST_PASSWORD)
        self.assertTrue(user["password_hash"].startswith("$argon2id$"))
        self.assertNotIn(TEST_PASSWORD, user["password_hash"])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.assertEqual(self.register(username="first").status_code, 201)
        response = self.register(username="second", email="FIRST@example.com")

        self.assertEqual(response.status_code, 409)
        self.assertIn("email", response.json()["detail"].lower())

    def test_duplicate_username_is_rejected_case_insensitively(self):
        self.assertEqual(self.register(username="First").status_code, 201)
        response = self.register(username="first", email="other@example.com")

        self.assertEqual(response.status_code, 409)
        self.assertIn("username", response.json()["detail"].lower())

    def test_weak_password_is_rejected(self):
        response = self.register(password="short1")

        self.assertEqual(response.status_code, 422)

    def test_mismatched_confirmation_is_rejected(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "username": "mismatch",
                "email": "mismatch@example.com",
                "password": TEST_PASSWORD,
                "confirm_password": TEST_PASSWORD + "x",
            },
        )

        self.assertEqual(response.status_code, 422)


class LoginLogoutTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("login-user", email="login@example.com")

    def test_login_success_and_profile(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "login-user")
        self.assertIn("ideon_session", response.cookies)

        profile = self.client.get("/api/auth/me")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["id"], self.user["id"])
        self.assertNotIn("password_hash", profile.json())

    def test_login_failure_is_generic(self):
        wrong_password = self.client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "WrongPassword9"},
        )
        unknown_email = self.client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": TEST_PASSWORD},
        )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(
            wrong_password.json()["detail"], unknown_email.json()["detail"]
        )
        self.assertNotIn("ideon_session", self.client.cookies)

    def test_logout_invalidates_session(self):
        login_client(self.client, "login@example.com")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_session_cookie_is_rejected(self):
        self.client.cookies.set("ideon_session", "not-a-real-token")

        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/ideas").status_code, 401)

    def test_expired_session_is_rejected_and_purged(self):
        login_client(self.client, "login@example.com")
        with closing(database.get_connection()) as connection, connection:
            connection.execute("UPDATE auth_sessions SET expires_at = 0")
            connection.commit()

        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        with closing(database.get_connection()) as connection, connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM auth_sessions"
            ).fetchone()["count"]
        self.assertEqual(count, 0)

    def test_unauthenticated_private_endpoints_return_401(self):
        calls = [
            ("get", "/api/ideas"),
            ("get", "/api/shortcuts"),
            ("get", "/api/website-tracker/websites"),
            ("post", "/api/ideas"),
        ]
        for method, path in calls:
            with self.subTest(path=path):
                response = getattr(self.client, method)(
                    path,
                    **(
                        {"json": {"title": "x", "description": "y"}}
                        if method == "post"
                        else {}
                    ),
                )
                self.assertEqual(response.status_code, 401)

    def test_csrf_header_is_required_for_mutations(self):
        login_client(self.client, "login@example.com")
        # Drop the CSRF header while keeping the session cookie.
        self.client.headers.pop("X-CSRF-Token", None)

        response = self.client.post(
            "/api/ideas",
            json={"title": "No CSRF", "description": "Rejected."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", response.json()["detail"])

    def test_csrf_token_must_match_the_session(self):
        login_client(self.client, "login@example.com")
        self.client.cookies.set("ideon_csrf", "forged-token")
        self.client.headers.update({"X-CSRF-Token": "forged-token"})

        response = self.client.post(
            "/api/ideas",
            json={"title": "Forged CSRF", "description": "Rejected."},
        )

        self.assertEqual(response.status_code, 403)

    def test_disallowed_origin_is_rejected(self):
        login_client(self.client, "login@example.com")
        csrf = self.client.cookies.get("ideon_csrf")

        response = self.client.post(
            "/api/ideas",
            headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
            json={"title": "Cross origin", "description": "Rejected."},
        )

        self.assertEqual(response.status_code, 403)


class IsolationTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = TestClient(app)
        self.client_b = TestClient(app)
        self.user_a = authenticated_user(self.client_a, "alice")
        self.user_b = authenticated_user(self.client_b, "bob")
        self.idea_a = insert_idea(
            "Alice idea", "Alice private body.", user_id=self.user_a["id"]
        )
        self.idea_b = insert_idea(
            "Bob idea", "Bob private body.", user_id=self.user_b["id"]
        )

    def test_lists_only_own_ideas(self):
        response = self.client_a.get("/api/ideas")

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()]
        self.assertIn(self.idea_a, ids)
        self.assertNotIn(self.idea_b, ids)

    def test_cannot_read_another_users_idea(self):
        response = self.client_a.get(f"/api/ideas/{self.idea_b}")

        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_another_users_idea(self):
        response = self.client_a.patch(
            f"/api/ideas/{self.idea_b}",
            json={"title": "Hijacked", "description": "Hijacked body."},
        )

        self.assertEqual(response.status_code, 404)
        with closing(database.get_connection()) as connection, connection:
            row = connection.execute(
                "SELECT title FROM ideas WHERE id = ?", (self.idea_b,)
            ).fetchone()
        self.assertEqual(row["title"], "Bob idea")

    def test_cannot_delete_another_users_idea(self):
        response = self.client_a.delete(f"/api/ideas/{self.idea_b}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client_b.get(f"/api/ideas/{self.idea_b}").status_code, 200
        )

    def test_assessment_history_is_isolated(self):
        self.client_b.post(
            f"/api/ideas/{self.idea_b}/assessment/prepare"
        )
        # Directly insert an assessment owned by Bob to avoid Gemini.
        with closing(database.get_connection()) as connection, connection:
            connection.execute(
                """
                INSERT INTO assessments (
                    user_id, idea_id, idea_title, idea_description,
                    analysis_json, scoring_json, final_score, classification
                )
                VALUES (?, ?, ?, ?, ?, ?, 50, 'Moderate')
                """,
                (self.user_b["id"], self.idea_b, "Bob idea", "Bob body.", VALID_ANALYSIS, VALID_SCORING),
            )
            connection.commit()

        self.assertEqual(
            self.client_b.get(
                f"/api/ideas/{self.idea_b}/assessments"
            ).status_code,
            200,
        )
        response = self.client_a.get(
            f"/api/ideas/{self.idea_b}/assessments"
        )
        self.assertEqual(response.status_code, 404)

    def test_improvement_sessions_and_revisions_are_isolated(self):
        with closing(database.get_connection()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO assessments (
                    user_id, idea_id, idea_title, idea_description,
                    analysis_json, scoring_json, final_score, classification
                )
                VALUES (?, ?, ?, ?, ?, ?, 50, 'Moderate')
                """,
                (self.user_b["id"], self.idea_b, "Bob idea", "Bob body.", VALID_ANALYSIS, VALID_SCORING),
            )
            assessment_id = cursor.lastrowid
            session_cursor = connection.execute(
                """
                INSERT INTO improvement_sessions (
                    user_id, idea_id, base_assessment_id, status,
                    accepted_revision_count
                )
                VALUES (?, ?, ?, 'active', 0)
                """,
                (self.user_b["id"], self.idea_b, assessment_id),
            )
            session_id = session_cursor.lastrowid
            connection.commit()

        # Bob sees his own session; Alice cannot see or mutate it.
        self.assertEqual(
            self.client_b.get(
                f"/api/ideas/{self.idea_b}/improvement/session/active"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_a.get(
                f"/api/ideas/{self.idea_b}/improvement/session/active"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_a.post(
                f"/api/ideas/{self.idea_b}/improvement/session"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_a.post(
                f"/api/ideas/{self.idea_b}/improvement/session/"
                f"{session_id}/propose"
            ).status_code,
            404,
        )

    def test_shortcuts_are_per_user(self):
        created = self.client_a.post(
            "/api/shortcuts",
            json={"name": "Alice only", "url": "https://alice.example"},
        )
        self.assertEqual(created.status_code, 201)
        shortcut_id = created.json()["id"]

        self.assertNotIn(
            shortcut_id,
            [item["id"] for item in self.client_b.get("/api/shortcuts").json()],
        )
        self.assertEqual(
            self.client_b.delete(f"/api/shortcuts/{shortcut_id}").status_code,
            404,
        )


class AdminAccessTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.admin_client = TestClient(app)
        self.user_client = TestClient(app)
        self.admin = authenticated_user(
            self.admin_client, "site-admin", role="admin"
        )
        self.user = authenticated_user(self.user_client, "regular-user")

    def test_admin_can_access_website_tracker(self):
        response = self.admin_client.get("/api/website-tracker/websites")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 2)

    def test_regular_user_cannot_access_website_tracker(self):
        endpoints = [
            "/api/website-tracker/websites",
            "/api/website-tracker/urls",
            "/api/website-tracker/sitemaps",
            "/api/website-tracker/activities",
        ]
        for path in endpoints:
            with self.subTest(path=path):
                response = self.user_client.get(path)
                self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_import_or_modify_sitemaps(self):
        imported = self.user_client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["sitemap.xml"]},
        )
        activity = self.user_client.post(
            "/api/website-tracker/activities",
            json={
                "title": "Nope",
                "description": "",
                "activity_type": "SEO Update",
                "status": "planned",
            },
        )

        self.assertEqual(imported.status_code, 403)
        self.assertEqual(activity.status_code, 403)
        self.assertEqual(
            self.user_client.delete("/api/website-tracker/activities/1").status_code,
            403,
        )


class LegacyMigrationTests(unittest.TestCase):
    """A legacy database without users must migrate without losing data."""

    LEGACY_SCHEMA = """
    CREATE TABLE ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z',
        updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z'
    );
    CREATE TABLE assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL,
        idea_title TEXT NOT NULL,
        idea_description TEXT NOT NULL,
        analysis_json TEXT NOT NULL,
        scoring_json TEXT NOT NULL,
        final_score REAL NOT NULL,
        classification TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT '2026-01-02T00:00:00Z'
    );
    CREATE TABLE improvement_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL,
        base_assessment_id INTEGER NOT NULL,
        current_revision_id INTEGER,
        status TEXT NOT NULL,
        accepted_revision_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT '2026-01-03T00:00:00Z',
        updated_at TEXT NOT NULL DEFAULT '2026-01-03T00:00:00Z'
    );
    CREATE TABLE improvement_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        proposal_attempt INTEGER NOT NULL,
        input_revision_id INTEGER,
        input_assessment_id INTEGER NOT NULL,
        proposed_title TEXT NOT NULL,
        proposed_description TEXT NOT NULL,
        rationale TEXT NOT NULL,
        key_changes_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT '2026-01-04T00:00:00Z'
    );
    CREATE TABLE idea_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        proposal_id INTEGER NOT NULL,
        revision_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        assessment_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT '2026-01-05T00:00:00Z'
    );
    CREATE TABLE web_shortcuts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Custom',
        created_at TEXT NOT NULL DEFAULT '2026-01-06T00:00:00Z',
        updated_at TEXT NOT NULL DEFAULT '2026-01-06T00:00:00Z'
    );
    INSERT INTO ideas (id, title, description)
        VALUES (7, 'Legacy idea', 'Preserved body.');
    INSERT INTO assessments (
        id, idea_id, idea_title, idea_description, analysis_json,
        scoring_json, final_score, classification
    ) VALUES (11, 7, 'Legacy idea', 'Preserved body.', '{}', '{}', 77, 'Strong');
    INSERT INTO improvement_sessions (
        id, idea_id, base_assessment_id, status, accepted_revision_count
    ) VALUES (13, 7, 11, 'completed', 1);
    INSERT INTO improvement_proposals (
        id, session_id, proposal_attempt, input_assessment_id,
        proposed_title, proposed_description, rationale,
        key_changes_json, status
    ) VALUES (17, 13, 1, 11, 'Better', 'Better body', 'Better', '[]', 'accepted');
    INSERT INTO idea_revisions (
        id, session_id, proposal_id, revision_number, title,
        description, assessment_id
    ) VALUES (19, 13, 17, 1, 'Better', 'Better body', 11);
    INSERT INTO web_shortcuts (id, name, url, category)
        VALUES (23, 'Legacy shortcut', 'https://legacy.example', 'Work');
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.previous_path = database.DATABASE_PATH
        self.addCleanup(self.restore_path)
        database.DATABASE_PATH = Path(self.temporary.name) / "legacy.db"

    def restore_path(self):
        database.DATABASE_PATH = self.previous_path

    def create_legacy_database(self):
        connection = sqlite3.connect(database.DATABASE_PATH)
        connection.executescript(self.LEGACY_SCHEMA)
        connection.commit()
        connection.close()

    def test_migration_preserves_and_claims_legacy_records(self):
        self.create_legacy_database()
        database.initialize_database()

        profile, created = auth_service.create_initial_admin(
            username="legacy-admin",
            email="legacy-admin@example.com",
            password=TEST_PASSWORD,
        )
        self.assertTrue(created)
        self.assertEqual(profile["role"], "admin")

        with closing(database.get_connection()) as connection, connection:
            for table, identifier, expected in (
                ("ideas", 7, profile["id"]),
                ("assessments", 11, profile["id"]),
                ("improvement_sessions", 13, profile["id"]),
                ("improvement_proposals", 17, profile["id"]),
                ("idea_revisions", 19, profile["id"]),
                ("web_shortcuts", 23, profile["id"]),
            ):
                with self.subTest(table=table):
                    row = connection.execute(
                        f"SELECT id, user_id FROM {table} WHERE id = ?",
                        (identifier,),
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row["user_id"], expected)

            idea = connection.execute(
                "SELECT title, created_at FROM ideas WHERE id = 7"
            ).fetchone()
            assessment = connection.execute(
                "SELECT idea_id, created_at FROM assessments WHERE id = 11"
            ).fetchone()
            session = connection.execute(
                "SELECT base_assessment_id, current_revision_id FROM "
                "improvement_sessions WHERE id = 13"
            ).fetchone()
            revision = connection.execute(
                "SELECT session_id, proposal_id, assessment_id "
                "FROM idea_revisions WHERE id = 19"
            ).fetchone()

        self.assertEqual(idea["title"], "Legacy idea")
        self.assertEqual(idea["created_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(assessment["idea_id"], 7)
        self.assertEqual(assessment["created_at"], "2026-01-02T00:00:00Z")
        self.assertEqual(session["base_assessment_id"], 11)
        self.assertEqual(revision["session_id"], 13)
        self.assertEqual(revision["proposal_id"], 17)
        self.assertEqual(revision["assessment_id"], 11)

    def test_migration_is_idempotent(self):
        self.create_legacy_database()
        database.initialize_database()

        first, created = auth_service.create_initial_admin(
            username="legacy-admin",
            email="legacy-admin@example.com",
            password=TEST_PASSWORD,
        )
        self.assertTrue(created)

        second, created_again = auth_service.create_initial_admin(
            username="different-admin",
            email="different@example.com",
            password=TEST_PASSWORD,
        )
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(auth_store.count_users(), 1)

        database.initialize_database()
        with closing(database.get_connection()) as connection, connection:
            for table, identifier in (
                ("ideas", 7),
                ("assessments", 11),
                ("improvement_sessions", 13),
                ("improvement_proposals", 17),
                ("idea_revisions", 19),
                ("web_shortcuts", 23),
            ):
                row = connection.execute(
                    f"SELECT user_id FROM {table} WHERE id = ?",
                    (identifier,),
                ).fetchone()
                self.assertEqual(row["user_id"], first["id"])


if __name__ == "__main__":
    unittest.main()
