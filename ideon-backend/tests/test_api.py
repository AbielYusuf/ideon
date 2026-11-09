import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database

# Point the app at a disposable database before importing it.
_TEMPORARY = tempfile.TemporaryDirectory()
database.DATABASE_PATH = Path(_TEMPORARY.name) / "api-tests.db"
database.initialize_database()

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from assessment_service import AssessmentService  # noqa: E402
from gemini_service import GeminiService, GeminiUnavailableError  # noqa: E402
from tests.support import (  # noqa: E402
    ANALYSIS,
    CRITERIA,
    NARRATIVE,
    FakeGemini,
    authenticated_user,
    fresh_database,
    insert_idea,
)


class AssessmentApiTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.client = TestClient(main.app)
        self.user = authenticated_user(self.client, "api-user")
        self.idea_id = insert_idea(
            "Portal", "A portal to Japan.", user_id=self.user["id"]
        )
        self.gemini = FakeGemini()
        self.original_service = main.assessment_service
        main.assessment_service = AssessmentService(self.gemini)
        self.addCleanup(self.restore_service)

    def restore_service(self):
        main.assessment_service = self.original_service

    def score_payload(self, confirmed=True, title="Refined portal", description="Refined body."):
        return {
            "confirmed": confirmed,
            "analysis": NARRATIVE.model_dump(),
            "confirmed_title": title,
            "confirmed_description": description,
        }

    def test_prepare_returns_analysis_without_scores(self):
        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/prepare"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["idea"]["id"], self.idea_id)
        self.assertIn("summary", body["analysis"])
        self.assertIn("clarifying_questions", body["analysis"])
        self.assertNotIn("criteria", body["analysis"])
        self.assertNotIn("final_score", body["analysis"])

    def test_refine_processes_answers(self):
        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/refine",
            json={
                "analysis": ANALYSIS.model_dump(),
                "answers": [
                    {"question": "Who?", "answer": "Small studios."},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Refined portal")
        self.assertEqual(
            self.gemini.refine_calls[0][2],
            [{"question": "Who?", "answer": "Small studios."}],
        )

    def test_scoring_cannot_happen_before_confirmation(self):
        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(confirmed=False),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.gemini.score_calls, [])
        self.assertEqual(
            self.client.get(f"/api/ideas/{self.idea_id}/assessments").json(), []
        )

    def test_confirmed_score_returns_and_persists_result(self):
        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["final_score"], 82.0)
        self.assertEqual(body["classification"], "Strong")
        self.assertEqual(len(body["criteria"]), 5)
        self.assertEqual(body["evaluated_title"], "Refined portal")

        history = self.client.get(
            f"/api/ideas/{self.idea_id}/assessments"
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(history.json()[0]["id"], body["id"])

    def test_multiple_assessments_do_not_overwrite_each_other(self):
        first = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(title="First", description="First body."),
        )
        second = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(title="Second", description="Second body."),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        history = self.client.get(
            f"/api/ideas/{self.idea_id}/assessments"
        ).json()
        self.assertEqual(len(history), 2)
        self.assertEqual(
            {item["evaluated_title"] for item in history}, {"First", "Second"}
        )

    def test_missing_idea_returns_404(self):
        prepare = self.client.post("/api/ideas/9999/assessment/prepare")
        refine = self.client.post(
            "/api/ideas/9999/assessment/refine",
            json={"analysis": ANALYSIS.model_dump(), "answers": []},
        )
        score = self.client.post(
            "/api/ideas/9999/assessment/score", json=self.score_payload()
        )
        history = self.client.get("/api/ideas/9999/assessments")

        for response in (prepare, refine, score, history):
            self.assertEqual(response.status_code, 404)

    def test_invalid_ai_scores_return_502_and_do_not_persist(self):
        self.gemini.criteria = [CRITERIA[0]]

        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self.client.get(f"/api/ideas/{self.idea_id}/assessments").json(), []
        )

    def test_gemini_unavailable_returns_502(self):
        self.gemini.error = GeminiUnavailableError("Gemini is down.")

        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/prepare"
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Gemini is down", response.json()["detail"])

    def test_missing_api_key_returns_503(self):
        main.assessment_service = AssessmentService(GeminiService())

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post(
                f"/api/ideas/{self.idea_id}/assessment/prepare"
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

    def test_blank_confirmed_text_is_rejected(self):
        response = self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json=self.score_payload(title="   "),
        )

        self.assertEqual(response.status_code, 422)


class ExistingFeatureTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.client = TestClient(main.app)
        authenticated_user(self.client, "feature-user")

    def test_health_create_list_read_update_delete(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)

        created = self.client.post(
            "/api/ideas",
            json={"title": "Existing flow", "description": "Works."},
        )
        self.assertEqual(created.status_code, 201)
        idea = created.json()

        listed = self.client.get("/api/ideas")
        self.assertEqual(listed.status_code, 200)
        self.assertIn(idea["id"], [item["id"] for item in listed.json()])

        detail = self.client.get(f"/api/ideas/{idea['id']}")
        self.assertEqual(detail.status_code, 200)

        updated = self.client.patch(
            f"/api/ideas/{idea['id']}",
            json={"title": "Updated", "description": "Updated body."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertNotEqual(updated.json()["updated_at"], idea["updated_at"])

        invalid = self.client.patch(
            f"/api/ideas/{idea['id']}",
            json={"title": "   ", "description": "   "},
        )
        self.assertEqual(invalid.status_code, 422)

        missing = self.client.get("/api/ideas/9999")
        self.assertEqual(missing.status_code, 404)

        deleted = self.client.delete(f"/api/ideas/{idea['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.get(f"/api/ideas/{idea['id']}").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
