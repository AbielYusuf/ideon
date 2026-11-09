"""Unit tests for Quick Access Web Shortcuts."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import database

_TEMPORARY = tempfile.TemporaryDirectory()
database.DATABASE_PATH = Path(_TEMPORARY.name) / "shortcut-tests.db"
database.initialize_database()

from main import app  # noqa: E402
from tests.support import authenticated_user, fresh_database  # noqa: E402


class WebShortcutsTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.client = TestClient(app)
        authenticated_user(self.client, "shortcut-user")

    def test_default_shortcuts_seeded(self):
        resp = self.client.get("/api/shortcuts")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertGreaterEqual(len(items), 4)
        names = [item["name"] for item in items]
        self.assertIn("ChatGPT", names)
        self.assertIn("EOS Teknologi Website", names)

    def test_create_shortcut_valid(self):
        payload = {
            "name": "GitHub",
            "url": "https://github.com",
            "category": "Development",
        }
        resp = self.client.post("/api/shortcuts", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "GitHub")
        self.assertEqual(data["url"], "https://github.com")
        self.assertEqual(data["category"], "Development")

    def test_create_shortcut_invalid_url_scheme(self):
        # Reject non-http/https schemes like file:// or javascript:
        payload = {
            "name": "Malicious",
            "url": "javascript:alert(1)",
        }
        resp = self.client.post("/api/shortcuts", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_update_shortcut(self):
        resp = self.client.post(
            "/api/shortcuts",
            json={"name": "Initial", "url": "https://example.com"},
        )
        shortcut_id = resp.json()["id"]

        update_resp = self.client.patch(
            f"/api/shortcuts/{shortcut_id}",
            json={"name": "Updated", "url": "https://example.org", "category": "Work"},
        )
        self.assertEqual(update_resp.status_code, 200)
        updated = update_resp.json()
        self.assertEqual(updated["name"], "Updated")
        self.assertEqual(updated["url"], "https://example.org")

    def test_delete_shortcut(self):
        resp = self.client.post(
            "/api/shortcuts",
            json={"name": "ToDelete", "url": "https://delete.me"},
        )
        shortcut_id = resp.json()["id"]

        del_resp = self.client.delete(f"/api/shortcuts/{shortcut_id}")
        self.assertEqual(del_resp.status_code, 204)

        # Confirm deleted
        all_resp = self.client.get("/api/shortcuts")
        ids = [item["id"] for item in all_resp.json()]
        self.assertNotIn(shortcut_id, ids)
