import unittest

from assessment_models import (
    ClarificationAnswer,
    RefineRequest,
    ScoreRequest,
)
from assessment_service import (
    AssessmentService,
    ConfirmationRequiredError,
    IdeaNotFoundError,
)
from gemini_service import GeminiUnavailableError
from scoring import ScoringError
from tests.support import (
    ANALYSIS,
    CRITERIA,
    NARRATIVE,
    FakeGemini,
    create_user,
    fresh_database,
    insert_idea,
)


def score_request(title="Refined portal", description="Refined description.", confirmed=True):
    return ScoreRequest(
        confirmed=confirmed,
        analysis=NARRATIVE,
        confirmed_title=title,
        confirmed_description=description,
    )


class PrepareAndRefineTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.user = create_user("assess-user")
        self.idea_id = insert_idea(
            "Portal", "A portal to Japan.", user_id=self.user["id"]
        )
        self.gemini = FakeGemini()
        self.service = AssessmentService(self.gemini)

    def test_prepare_uses_the_stored_idea(self):
        result = self.service.prepare(self.idea_id, self.user["id"])

        self.assertEqual(result.idea.id, self.idea_id)
        self.assertEqual(result.idea.title, "Portal")
        self.assertEqual(result.analysis, ANALYSIS)
        self.assertEqual(self.gemini.prepare_calls[0].description, "A portal to Japan.")

    def test_refine_passes_answers_and_ignores_blank_ones(self):
        request = RefineRequest(
            analysis=ANALYSIS,
            answers=[
                ClarificationAnswer(question="Who?", answer="Small studios."),
                ClarificationAnswer(question="Budget?", answer="   "),
            ],
        )

        result = self.service.refine(self.idea_id, request, self.user["id"])

        self.assertEqual(result.title, "Refined portal")
        answers = self.gemini.refine_calls[0][2]
        self.assertEqual(
            answers, [{"question": "Who?", "answer": "Small studios."}]
        )

    def test_missing_idea_is_rejected(self):
        with self.assertRaises(IdeaNotFoundError):
            self.service.prepare(9999, self.user["id"])


class ScoringWorkflowTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.user = create_user("assess-user")
        self.idea_id = insert_idea(
            "Portal", "A portal to Japan.", user_id=self.user["id"]
        )
        self.gemini = FakeGemini()
        self.service = AssessmentService(self.gemini)

    def test_scoring_requires_explicit_confirmation(self):
        with self.assertRaises(ConfirmationRequiredError):
            self.service.score(
                self.idea_id, score_request(confirmed=False), self.user["id"]
            )

        self.assertEqual(self.gemini.score_calls, [])
        self.assertEqual(self.service.history(self.idea_id, self.user["id"]), [])

    def test_confirmed_score_is_calculated_and_persisted(self):
        result = self.service.score(self.idea_id, score_request(), self.user["id"])

        self.assertEqual(result.final_score, 82.0)
        self.assertEqual(result.classification, "Strong")
        self.assertEqual(len(result.criteria), 5)
        self.assertEqual(result.evaluated_title, "Refined portal")
        self.assertEqual(result.evaluated_description, "Refined description.")
        self.assertEqual(self.gemini.score_calls[0][2], "Refined portal")
        self.assertEqual(self.gemini.score_calls[0][3], "Refined description.")

        history = self.service.history(self.idea_id, self.user["id"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].id, result.id)

    def test_multiple_assessments_preserve_older_snapshots(self):
        first = self.service.score(
            self.idea_id,
            score_request(title="First title", description="First body."),
            self.user["id"],
        )
        second = self.service.score(
            self.idea_id,
            score_request(title="Second title", description="Second body."),
            self.user["id"],
        )

        history = self.service.history(self.idea_id, self.user["id"])

        self.assertEqual(len(history), 2)
        self.assertEqual({item.id for item in history}, {first.id, second.id})
        self.assertEqual(
            {item.evaluated_title for item in history},
            {"First title", "Second title"},
        )
        self.assertEqual(history[0].id, second.id)

    def test_invalid_ai_criteria_are_rejected_without_persisting(self):
        self.gemini.criteria = [dict(CRITERIA[0])]
        self.gemini.criteria[0]["score"] = 101

        with self.assertRaises(ScoringError):
            self.service.score(self.idea_id, score_request(), self.user["id"])

        self.assertEqual(self.service.history(self.idea_id, self.user["id"]), [])

    def test_gemini_failure_does_not_report_success(self):
        self.gemini.error = GeminiUnavailableError("Gemini is down.")

        with self.assertRaises(GeminiUnavailableError):
            self.service.score(self.idea_id, score_request(), self.user["id"])

        self.assertEqual(self.service.history(self.idea_id, self.user["id"]), [])

    def test_missing_idea_is_rejected(self):
        with self.assertRaises(IdeaNotFoundError):
            self.service.score(9999, score_request(), self.user["id"])


if __name__ == "__main__":
    unittest.main()
