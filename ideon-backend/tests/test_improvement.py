"""Comprehensive unit tests for the Phase 5 Manual Improvement Loop."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import database

# Point imports at a disposable database when this file runs on its own.
_TEMPORARY = tempfile.TemporaryDirectory()
database.DATABASE_PATH = Path(_TEMPORARY.name) / "improvement-tests.db"
database.initialize_database()

from improvement_models import GeneratedProposalContent
from improvement_service import (
    ImprovementService,
    InvalidProposalStateError,
    InvalidSessionStateError,
    MaximumRevisionsReachedError,
)
import improvement_store as store
from main import app
from tests.support import (
    FakeGemini,
    authenticated_user,
    create_user,
    fresh_database,
    insert_idea,
)


class ImprovementFakeGemini(FakeGemini):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.propose_calls = []
        self.proposal_content = GeneratedProposalContent(
            proposed_title="Improved Idea Title",
            proposed_description="An improved and clarified idea description.",
            rationale="Addresses key weaknesses identified in assessment.",
            key_changes=["Addressed cost structure", "Clarified target market"],
        )

    def generate_improvement_proposal(
        self, current_title, current_description, latest_assessment, iteration_number
    ):
        self.propose_calls.append(
            (current_title, current_description, latest_assessment, iteration_number)
        )
        if self.error:
            raise self.error
        return self.proposal_content


class ImprovementLoopTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.gemini = ImprovementFakeGemini()
        self.service = ImprovementService(self.gemini)
        self.user = create_user("improve-user")
        self.idea_id = insert_idea(
            "Original Title", "Original Description", user_id=self.user["id"]
        )

    def _create_baseline_assessment(self, idea_id: int):
        from assessment_service import AssessmentService
        from assessment_models import ScoreRequest, AssessmentNarrative
        ass_service = AssessmentService(self.gemini)
        narrative = AssessmentNarrative(
            summary="Initial baseline summary",
            key_strengths=["Clear goal"],
            key_weaknesses=["Lacks pricing detail"],
            missing_information=["Budget breakdown"],
            critical_assumptions=["Market is ready"],
            uncertainty_notes=["Conversion rate uncertain"],
        )
        return ass_service.score(
            idea_id,
            ScoreRequest(
                confirmed=True,
                analysis=narrative,
                confirmed_title="Original Title",
                confirmed_description="Original Description",
            ),
            self.user["id"],
        )

    def test_start_session_requires_assessment(self):
        """Cannot start session if no prior assessment exists."""
        with self.assertRaises(InvalidSessionStateError):
            self.service.start_session(self.idea_id, self.user["id"])

    def test_start_session_success(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])
        self.assertEqual(session.idea_id, self.idea_id)
        self.assertEqual(session.status, "active")
        self.assertEqual(session.accepted_revision_count, 0)
        self.assertIsNone(session.current_revision_id)

    def test_propose_creates_pending_proposal(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])

        proposal = self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )
        self.assertEqual(proposal.session_id, session.id)
        self.assertEqual(proposal.status, "pending")
        self.assertEqual(proposal.proposed_title, "Improved Idea Title")
        self.assertEqual(proposal.proposal_attempt, 1)

    def test_reject_proposal_does_not_increment_counter(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])
        proposal = self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )

        res = self.service.action_proposal(
            self.idea_id, session.id, proposal.id, "reject", self.user["id"]
        )
        self.assertEqual(res.action, "reject")
        self.assertEqual(res.proposal.status, "rejected")
        self.assertEqual(res.session.accepted_revision_count, 0)
        self.assertIsNone(res.session.current_revision_id)

    def test_regenerate_proposal_supersedes_and_generates_new(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])
        proposal1 = self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )

        res = self.service.action_proposal(
            self.idea_id,
            session.id,
            proposal1.id,
            "regenerate",
            self.user["id"],
        )
        self.assertEqual(res.action, "regenerate")
        self.assertEqual(res.proposal.status, "superseded")
        self.assertEqual(res.session.accepted_revision_count, 0)
        self.assertIsNotNone(res.next_proposal)
        self.assertEqual(res.next_proposal.proposal_attempt, 2)
        self.assertEqual(res.next_proposal.status, "pending")

    def test_accept_proposal_creates_revision_and_assessment_and_preserves_original(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])
        proposal = self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )

        res = self.service.action_proposal(
            self.idea_id, session.id, proposal.id, "accept", self.user["id"]
        )
        self.assertEqual(res.action, "accept")
        self.assertEqual(res.session.accepted_revision_count, 1)
        self.assertEqual(res.proposal.status, "accepted")
        self.assertIsNotNone(res.revision)
        self.assertEqual(res.revision.revision_number, 1)
        self.assertEqual(res.revision.title, "Improved Idea Title")
        self.assertIsNotNone(res.comparison)

        # CRITICAL 1: Verify original idea is UNTOUCHED
        from assessment_service import _load_idea
        original = _load_idea(self.idea_id, self.user["id"])
        self.assertEqual(original.title, "Original Title")
        self.assertEqual(original.description, "Original Description")

    def test_maximum_5_accepted_revisions_limit(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])

        for i in range(1, 6):
            proposal = self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )
            res = self.service.action_proposal(
                self.idea_id, session.id, proposal.id, "accept", self.user["id"]
            )
            self.assertEqual(res.session.accepted_revision_count, i)

        # After 5th accepted revision, session must be 'completed'
        detail = self.service.get_session_detail(session.id, self.user["id"])
        self.assertEqual(detail.session.status, "completed")
        self.assertEqual(detail.session.accepted_revision_count, 5)

        # Revision 6 must be IMPOSSIBLE
        with self.assertRaises(InvalidSessionStateError):
            self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )

    def test_stop_session(self):
        self._create_baseline_assessment(self.idea_id)
        session = self.service.start_session(self.idea_id, self.user["id"])
        stopped = self.service.stop_session(
            self.idea_id, session.id, self.user["id"]
        )
        self.assertEqual(stopped.status, "cancelled")

        with self.assertRaises(InvalidSessionStateError):
            self.service.propose(
                self.idea_id, session.id, self.user["id"]
            )


class ImprovementApiTests(unittest.TestCase):
    def setUp(self):
        fresh_database(self)
        self.fake_gemini = ImprovementFakeGemini()
        # Patch app gemini and services
        import main
        main.improvement_service = ImprovementService(self.fake_gemini)
        from assessment_service import AssessmentService
        main.assessment_service = AssessmentService(self.fake_gemini)
        self.client = TestClient(app)
        self.user = authenticated_user(self.client, "improve-api-user")
        self.idea_id = insert_idea(
            "API Idea", "API Idea Description", user_id=self.user["id"]
        )

    def _score_initial(self):
        # Prepare & refine & score
        self.client.post(f"/api/ideas/{self.idea_id}/assessment/prepare")
        self.client.post(
            f"/api/ideas/{self.idea_id}/assessment/score",
            json={
                "confirmed": True,
                "analysis": {
                    "summary": "OK",
                    "key_strengths": ["s"],
                    "key_weaknesses": ["w"],
                    "missing_information": ["m"],
                    "critical_assumptions": ["a"],
                    "uncertainty_notes": ["u"],
                },
                "confirmed_title": "API Idea",
                "confirmed_description": "API Idea Description",
            },
        )

    def test_api_full_improvement_flow(self):
        self._score_initial()

        # Start session
        resp = self.client.post(f"/api/ideas/{self.idea_id}/improvement/session")
        self.assertEqual(resp.status_code, 201)
        session_id = resp.json()["id"]

        # Propose
        resp = self.client.post(f"/api/ideas/{self.idea_id}/improvement/session/{session_id}/propose")
        self.assertEqual(resp.status_code, 201)
        prop_id = resp.json()["id"]

        # Accept
        resp = self.client.post(
            f"/api/ideas/{self.idea_id}/improvement/session/{session_id}/proposals/{prop_id}/action",
            json={"action": "accept"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["action"], "accept")
        self.assertEqual(data["session"]["accepted_revision_count"], 1)

        # Check active session detail endpoint
        resp = self.client.get(f"/api/ideas/{self.idea_id}/improvement/session/active")
        self.assertEqual(resp.status_code, 200)
        detail = resp.json()
        self.assertEqual(detail["session"]["accepted_revision_count"], 1)
        self.assertEqual(len(detail["revisions"]), 1)
