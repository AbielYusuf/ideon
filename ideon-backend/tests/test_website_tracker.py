"""Tests for Website Tracker parsing, import, URLs, and activities."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
import website_tracker_service

# Keep module import from touching the live database when this file runs alone.
_TEMPORARY = tempfile.TemporaryDirectory()
database.DATABASE_PATH = Path(_TEMPORARY.name) / "website-tracker-tests.db"
database.initialize_database()

from main import app  # noqa: E402
from website_tracker_sitemap import normalize_url, parse_sitemap  # noqa: E402
from tests.support import authenticated_user, fresh_database  # noqa: E402

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://eosteknologi.com/</loc><lastmod>2026-11-06</lastmod></url>
  <url><loc> https://eosteknologi.com/blog/ </loc></url>
  <url><loc>https://eosteknologi.com/about-us/</loc></url>
  <url><loc>not-a-url</loc></url>
</urlset>
"""

INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://eosteknologi.com/child.xml</loc></sitemap>
  <sitemap><loc>https://elsewhere.example/remote.xml</loc></sitemap>
</sitemapindex>
"""

CHILD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://eosteknologi.com/child-page/</loc></url>
</urlset>
"""

INDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://eosindobisnis.com/</loc><lastmod>2026-11-06</lastmod></url>
  <url><loc>https://www.eosindobisnis.com/pricing</loc></url>
  <url><loc>https://unrelated.example.com/landing</loc></url>
  <url><loc>not-a-url</loc></url>
</urlset>
"""


class WebsiteMigrationTests(unittest.TestCase):
    """Legacy single-website databases must migrate in place and idempotently."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "legacy.db"
        self.previous_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.path
        self.addCleanup(self.restore_path)

        connection = sqlite3.connect(self.path)
        connection.executescript(
            """
            CREATE TABLE website_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                sitemap_last_modified TEXT,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            );
            CREATE TABLE website_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                activity_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('planned', 'completed')),
                website_url_id INTEGER,
                planned_date TEXT NOT NULL,
                completed_date TEXT,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                FOREIGN KEY (website_url_id) REFERENCES website_urls(id)
                    ON DELETE SET NULL
            );
            INSERT INTO website_urls (id, url, sitemap_last_modified)
            VALUES (10, 'https://eosteknologi.com/', '2026-11-01');
            INSERT INTO website_urls (id, url)
            VALUES (20, 'https://eosteknologi.com/blog/');
            INSERT INTO website_activities (
                id, title, activity_type, status, website_url_id, planned_date
            )
            VALUES (5, 'Legacy activity', 'SEO Update', 'planned', 10, '2026-11-08');
            INSERT INTO website_activities (
                id, title, activity_type, status, website_url_id, planned_date
            )
            VALUES (6, 'General activity', 'Other', 'completed', NULL, '2026-11-09');
            """
        )
        connection.commit()
        connection.close()

    def restore_path(self):
        database.DATABASE_PATH = self.previous_path

    def rows(self, query, parameters=()):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(query, parameters)]
        finally:
            connection.close()

    def test_migration_preserves_ids_activities_and_is_idempotent(self):
        database.initialize_database()
        database.initialize_database()

        websites = self.rows("SELECT id, name, domain FROM websites ORDER BY id")
        self.assertEqual(
            websites,
            [
                {"id": 1, "name": "EOS Teknologi", "domain": "eosteknologi.com"},
                {"id": 2, "name": "EOS Indo Bisnis", "domain": "eosindobisnis.com"},
            ],
        )

        urls = self.rows("SELECT id, website_id, url FROM website_urls ORDER BY id")
        self.assertEqual([item["id"] for item in urls], [10, 20])
        self.assertTrue(all(item["website_id"] == 1 for item in urls))

        activities = self.rows(
            "SELECT id, website_id, website_url_id FROM website_activities ORDER BY id"
        )
        self.assertEqual(
            activities,
            [
                {"id": 5, "website_id": 1, "website_url_id": 10},
                {"id": 6, "website_id": 1, "website_url_id": None},
            ],
        )

        # URL uniqueness is scoped per website: the same URL may be registered
        # under another website, but not twice under the same one.
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                """
                INSERT INTO website_urls (website_id, url)
                VALUES (2, 'https://eosteknologi.com/')
                """
            )
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO website_urls (website_id, url)
                    VALUES (1, 'https://eosteknologi.com/')
                    """
                )
                connection.commit()
        finally:
            connection.close()



class SitemapParsingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_standard_urlset_with_namespace_and_lastmod(self):
        result = parse_sitemap(self.write("sitemap.xml", SITEMAP_XML))
        self.assertFalse(result.is_index)
        self.assertEqual(len(result.urls), 3)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.urls[0][0], "https://eosteknologi.com/")
        self.assertEqual(result.urls[0][1], "2026-11-06")
        self.assertEqual(
            result.urls[1][0], "https://eosteknologi.com/blog/"
        )

    def test_sitemap_index_detection(self):
        result = parse_sitemap(self.write("index.xml", INDEX_XML))
        self.assertTrue(result.is_index)
        self.assertEqual(
            result.child_locations,
            [
                "https://eosteknologi.com/child.xml",
                "https://elsewhere.example/remote.xml",
            ],
        )

    def test_url_normalization_preserves_path_and_query(self):
        self.assertEqual(
            normalize_url(" HTTPS://EOSteknologi.com/Path/?a=1#section "),
            "https://eosteknologi.com/Path/?a=1",
        )
        self.assertIsNone(normalize_url("javascript:alert(1)"))
        self.assertIsNone(normalize_url("ftp://eosteknologi.com/file"))
        self.assertIsNone(normalize_url("not-a-url"))

    def test_unsafe_xml_is_rejected(self):
        path = self.write(
            "unsafe.xml",
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<urlset><url><loc>https://eosteknologi.com/</loc></url></urlset>",
        )
        from website_tracker_sitemap import SitemapError

        with self.assertRaises(SitemapError):
            parse_sitemap(path)


class WebsiteTrackerApiTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.client = TestClient(app)
        self.admin = authenticated_user(
            self.client, "tracker-admin", role="admin"
        )
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        patcher = patch.object(website_tracker_service, "PROJECT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name: str, content: str) -> None:
        (self.root / name).write_text(content, encoding="utf-8")

    def import_fixture(self) -> dict:
        self.write("sitemap.xml", SITEMAP_XML)
        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["sitemap.xml"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def urls(self, **params):
        response = self.client.get("/api/website-tracker/urls", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def create_activity(self, body: dict) -> dict:
        response = self.client.post(
            "/api/website-tracker/activities", json=body
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_import_summary_and_duplicate_prevention(self):
        summary = self.import_fixture()
        self.assertEqual(summary["found"], 4)
        self.assertEqual(summary["imported"], 3)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["duplicates"], 0)

        again = self.import_fixture()
        self.assertEqual(again["imported"], 0)
        self.assertEqual(again["duplicates"], 3)
        self.assertEqual(len(self.urls()), 3)

    def test_reimport_preserves_existing_activities(self):
        summary = self.import_fixture()
        self.assertEqual(summary["imported"], 3)
        url = self.urls()[0]
        activity = self.create_activity(
            {
                "title": "Update meta description",
                "description": "Rewrote the meta description.",
                "activity_type": "SEO Update",
                "status": "planned",
                "website_url_id": url["id"],
                "planned_date": "2026-11-08",
            }
        )

        self.import_fixture()
        detail = self.client.get(
            f"/api/website-tracker/urls/{url['id']}"
        )
        self.assertEqual(detail.status_code, 200)
        history = detail.json()["activities"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], activity["id"])

    def test_url_listing_search_and_status_filter(self):
        self.import_fixture()
        urls = self.urls()
        about = next(item for item in urls if item["url"].endswith("about-us/"))

        self.create_activity(
            {
                "title": "Fix broken CTA",
                "description": "",
                "activity_type": "CTA Update",
                "status": "planned",
                "website_url_id": about["id"],
                "planned_date": "2026-11-08",
            }
        )

        searched = self.urls(search="about-us")
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0]["id"], about["id"])

        planned = self.urls(status_filter="planned")
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]["planned_count"], 1)

        completed = self.urls(status_filter="completed")
        self.assertEqual(completed, [])

    def test_url_detail_and_activity_history(self):
        self.import_fixture()
        url = self.urls()[0]
        activity = self.create_activity(
            {
                "title": "Add internal links",
                "description": "Linked related service pages.",
                "activity_type": "Internal Linking",
                "status": "planned",
                "website_url_id": url["id"],
                "planned_date": "2026-11-08",
            }
        )

        detail = self.client.get(f"/api/website-tracker/urls/{url['id']}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["activity_count"], 1)
        self.assertEqual(payload["activities"][0]["id"], activity["id"])

        missing = self.client.get("/api/website-tracker/urls/9999")
        self.assertEqual(missing.status_code, 404)

    def test_planned_to_completed_preserves_dates(self):
        self.import_fixture()
        url = self.urls()[0]
        activity = self.create_activity(
            {
                "title": "Publish November update",
                "description": "Updated the hero section.",
                "activity_type": "Content Update",
                "status": "planned",
                "website_url_id": url["id"],
                "planned_date": "2026-11-08",
            }
        )
        self.assertIsNone(activity["completed_date"])

        response = self.client.post(
            f"/api/website-tracker/activities/{activity['id']}/complete",
            json={"completed_date": "2026-11-10"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        completed = response.json()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["planned_date"], "2026-11-08")
        self.assertEqual(completed["completed_date"], "2026-11-10")
        self.assertEqual(completed["website_url_id"], url["id"])

    def test_create_completed_activity_defaults_to_today(self):
        self.import_fixture()
        activity = self.create_activity(
            {
                "title": "Direct completion",
                "description": "Done without a plan.",
                "activity_type": "Other",
                "status": "completed",
                "planned_date": "2026-11-09",
            }
        )
        self.assertIsNotNone(activity["completed_date"])
        self.assertIsNone(activity["website_url_id"])

    def test_update_activity_fields_and_status(self):
        self.import_fixture()
        activity = self.create_activity(
            {
                "title": "Old title",
                "description": "Old notes.",
                "activity_type": "SEO Update",
                "status": "planned",
                "planned_date": "2026-11-08",
            }
        )

        response = self.client.patch(
            f"/api/website-tracker/activities/{activity['id']}",
            json={
                "title": "New title",
                "activity_type": "Technical Fix",
                "planned_date": "2026-11-12",
                "status": "completed",
                "completed_date": "2026-11-14",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertEqual(updated["title"], "New title")
        self.assertEqual(updated["activity_type"], "Technical Fix")
        self.assertEqual(updated["planned_date"], "2026-11-12")
        self.assertEqual(updated["completed_date"], "2026-11-14")

    def test_delete_activity_keeps_url(self):
        self.import_fixture()
        url = self.urls()[0]
        activity = self.create_activity(
            {
                "title": "Delete me",
                "description": "",
                "activity_type": "Other",
                "status": "planned",
                "website_url_id": url["id"],
                "planned_date": "2026-11-08",
            }
        )
        response = self.client.delete(
            f"/api/website-tracker/activities/{activity['id']}"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(self.urls()), 3)
        self.assertEqual(
            self.client.get(
                f"/api/website-tracker/activities/{activity['id']}"
            ).status_code,
            404,
        )

    def test_date_filter_includes_completion_date(self):
        self.import_fixture()
        activity = self.create_activity(
            {
                "title": "Planned and completed on different days",
                "description": "",
                "activity_type": "Content Update",
                "status": "planned",
                "planned_date": "2026-11-08",
            }
        )
        self.client.post(
            f"/api/website-tracker/activities/{activity['id']}/complete",
            json={"completed_date": "2026-11-10"},
        )

        planned_day = self.client.get(
            "/api/website-tracker/activities",
            params={"start": "2026-11-08", "end": "2026-11-08"},
        )
        completed_day = self.client.get(
            "/api/website-tracker/activities",
            params={"start": "2026-11-10", "end": "2026-11-10"},
        )
        self.assertEqual(len(planned_day.json()), 1)
        self.assertEqual(len(completed_day.json()), 1)
        self.assertEqual(
            planned_day.json()[0]["id"], completed_day.json()[0]["id"]
        )

    def test_invalid_activity_type_is_rejected(self):
        response = self.client.post(
            "/api/website-tracker/activities",
            json={
                "title": "Bad type",
                "activity_type": "Not a type",
                "planned_date": "2026-11-08",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_import_rejects_path_traversal_and_non_xml(self):
        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["../sitemap.xml"]},
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["notes.txt"]},
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["missing.xml"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_local_sitemap_index_imports_child_only(self):
        self.write("index.xml", INDEX_XML)
        self.write("child.xml", CHILD_XML)
        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": ["index.xml"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        summary = response.json()
        self.assertTrue(summary["sitemap_index"])
        self.assertEqual(summary["files_processed"], 2)
        self.assertEqual(summary["imported"], 1)
        self.assertEqual(summary["child_sitemaps_skipped"], 1)
        self.assertEqual(len(self.urls()), 1)

    def test_missing_url_association_returns_404(self):
        response = self.client.post(
            "/api/website-tracker/activities",
            json={
                "title": "Unknown URL",
                "activity_type": "Other",
                "planned_date": "2026-11-08",
                "website_url_id": 9999,
            },
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Multi-website behavior
    # ------------------------------------------------------------------

    def websites(self) -> dict[str, dict]:
        response = self.client.get("/api/website-tracker/websites")
        self.assertEqual(response.status_code, 200, response.text)
        return {item["domain"]: item for item in response.json()}

    def import_into(
        self, website_id: int, name: str, content: str
    ) -> dict:
        self.write(name, content)
        response = self.client.post(
            "/api/website-tracker/sitemaps/import",
            json={"filenames": [name], "website_id": website_id},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_websites_are_registered_once(self):
        websites = self.websites()
        self.assertEqual(
            set(websites),
            {"eosteknologi.com", "eosindobisnis.com"},
        )
        self.assertEqual(websites["eosteknologi.com"]["name"], "EOS Teknologi")
        self.assertEqual(websites["eosindobisnis.com"]["name"], "EOS Indo Bisnis")

        again = self.client.get("/api/website-tracker/websites")
        self.assertEqual(len(again.json()), 2)

    def test_indo_import_reports_and_rejects_unrelated_domains(self):
        websites = self.websites()
        indo_id = websites["eosindobisnis.com"]["id"]
        summary = self.import_into(indo_id, "indo.xml", INDO_XML)

        self.assertEqual(summary["website_id"], indo_id)
        self.assertEqual(summary["website_name"], "EOS Indo Bisnis")
        self.assertEqual(summary["found"], 4)
        self.assertEqual(summary["imported"], 2)
        self.assertEqual(summary["unrelated_domains"], 1)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["skipped"], 1)

        indo_urls = self.urls(website_id=indo_id)
        self.assertEqual(len(indo_urls), 2)
        self.assertEqual(
            {item["url"] for item in indo_urls},
            {
                "https://eosindobisnis.com/",
                "https://www.eosindobisnis.com/pricing",
            },
        )
        self.assertTrue(
            all(item["website_name"] == "EOS Indo Bisnis" for item in indo_urls)
        )

        tek_id = websites["eosteknologi.com"]["id"]
        self.assertEqual(self.urls(website_id=tek_id), [])

    def test_url_library_search_is_isolated_by_website(self):
        websites = self.websites()
        tek_id = websites["eosteknologi.com"]["id"]
        indo_id = websites["eosindobisnis.com"]["id"]
        self.import_fixture()
        self.import_into(indo_id, "indo.xml", INDO_XML)

        tek_urls = self.urls(website_id=tek_id)
        indo_urls = self.urls(website_id=indo_id)
        self.assertEqual(len(tek_urls), 3)
        self.assertEqual(len(indo_urls), 2)

        # The string "pricing" exists only on the Indo Bisnis site.
        self.assertEqual(self.urls(website_id=indo_id, search="pricing")[0]["website_id"], indo_id)
        self.assertEqual(self.urls(website_id=tek_id, search="pricing"), [])

    def test_url_detail_rejects_cross_website_context(self):
        websites = self.websites()
        tek_id = websites["eosteknologi.com"]["id"]
        indo_id = websites["eosindobisnis.com"]["id"]
        self.import_fixture()
        self.import_into(indo_id, "indo.xml", INDO_XML)

        tek_url = self.urls(website_id=tek_id)[0]
        wrong = self.client.get(
            f"/api/website-tracker/urls/{tek_url['id']}",
            params={"website_id": indo_id},
        )
        self.assertEqual(wrong.status_code, 404)

        right = self.client.get(
            f"/api/website-tracker/urls/{tek_url['id']}",
            params={"website_id": tek_id},
        )
        self.assertEqual(right.status_code, 200)
        self.assertEqual(right.json()["website_name"], "EOS Teknologi")

    def test_cross_website_activity_association_is_rejected(self):
        websites = self.websites()
        tek_id = websites["eosteknologi.com"]["id"]
        indo_id = websites["eosindobisnis.com"]["id"]
        self.import_into(indo_id, "indo.xml", INDO_XML)
        indo_url = self.urls(website_id=indo_id)[0]

        response = self.client.post(
            "/api/website-tracker/activities",
            json={
                "title": "Wrong website",
                "activity_type": "Other",
                "planned_date": "2026-11-08",
                "website_id": tek_id,
                "website_url_id": indo_url["id"],
            },
        )
        self.assertEqual(response.status_code, 400)

        # Omitting website_id derives it from the URL instead of trusting the
        # default website.
        created = self.create_activity(
            {
                "title": "Correctly scoped",
                "activity_type": "Other",
                "planned_date": "2026-11-08",
                "website_url_id": indo_url["id"],
            }
        )
        self.assertEqual(created["website_id"], indo_id)
        self.assertEqual(created["website_name"], "EOS Indo Bisnis")

    def test_activity_filtering_by_website(self):
        websites = self.websites()
        tek_id = websites["eosteknologi.com"]["id"]
        indo_id = websites["eosindobisnis.com"]["id"]
        self.create_activity(
            {
                "title": "Teknologi plan",
                "activity_type": "SEO Update",
                "status": "planned",
                "website_id": tek_id,
                "planned_date": "2026-11-08",
            }
        )
        self.create_activity(
            {
                "title": "Indo general",
                "activity_type": "Content Update",
                "status": "planned",
                "website_id": indo_id,
                "planned_date": "2026-11-09",
            }
        )

        tek_activities = self.client.get(
            "/api/website-tracker/activities", params={"website_id": tek_id}
        ).json()
        indo_activities = self.client.get(
            "/api/website-tracker/activities", params={"website_id": indo_id}
        ).json()
        all_activities = self.client.get("/api/website-tracker/activities").json()

        self.assertEqual([item["title"] for item in tek_activities], ["Teknologi plan"])
        self.assertEqual([item["title"] for item in indo_activities], ["Indo general"])
        self.assertEqual(len(all_activities), 2)

    def test_indo_reimport_preserves_activity_and_teknologi_data(self):
        websites = self.websites()
        tek_id = websites["eosteknologi.com"]["id"]
        indo_id = websites["eosindobisnis.com"]["id"]
        self.import_fixture()
        self.import_into(indo_id, "indo.xml", INDO_XML)

        indo_url = self.urls(website_id=indo_id)[0]
        activity = self.create_activity(
            {
                "title": "Indo activity",
                "activity_type": "SEO Update",
                "planned_date": "2026-11-08",
                "website_url_id": indo_url["id"],
            }
        )

        again = self.import_into(indo_id, "indo.xml", INDO_XML)
        self.assertEqual(again["imported"], 0)
        self.assertEqual(again["duplicates"], 2)

        detail = self.client.get(
            f"/api/website-tracker/urls/{indo_url['id']}",
            params={"website_id": indo_id},
        ).json()
        self.assertEqual([item["id"] for item in detail["activities"]], [activity["id"]])
        self.assertEqual(len(self.urls(website_id=tek_id)), 3)
        self.assertEqual(len(self.urls(website_id=indo_id)), 2)

    def test_unknown_website_filter_returns_404(self):
        response = self.client.get(
            "/api/website-tracker/urls", params={"website_id": 9999}
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
