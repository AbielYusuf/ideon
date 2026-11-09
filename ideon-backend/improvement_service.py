"""Orchestration service for the Phase 5 Manual Improvement Loop."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from assessment_models import AssessmentResult, CriterionResult, IdeaSnapshot
from assessment_service import _load_idea, _row_to_result
from gemini_service import GeminiService
from improvement_models import (
    IdeaRevisionResponse,
    ImprovementProposalResponse,
    ImprovementSessionDetailResponse,
    ImprovementSessionResponse,
    ProposalActionResponse,
    ScoreComparison,
    ScoreDelta,
)
import improvement_store as store
from scoring import score_assessment


class ImprovementError(Exception):
    """Base exception for improvement loop errors."""


class SessionNotFoundError(ImprovementError):
    pass


class ProposalNotFoundError(ImprovementError):
    pass


class InvalidSessionStateError(ImprovementError):
    pass


class InvalidProposalStateError(ImprovementError):
    pass


class MaximumRevisionsReachedError(ImprovementError):
    pass


class AssessmentMismatchError(ImprovementError):
    pass


def _row_to_session_response(row: sqlite3.Row) -> ImprovementSessionResponse:
    return ImprovementSessionResponse(
        id=row["id"],
        idea_id=row["idea_id"],
        base_assessment_id=row["base_assessment_id"],
        current_revision_id=row["current_revision_id"],
        status=row["status"],
        accepted_revision_count=row["accepted_revision_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_proposal_response(row: sqlite3.Row) -> ImprovementProposalResponse:
    key_changes = json.loads(row["key_changes_json"]) if row["key_changes_json"] else []
    return ImprovementProposalResponse(
        id=row["id"],
        session_id=row["session_id"],
        proposal_attempt=row["proposal_attempt"],
        input_revision_id=row["input_revision_id"],
        input_assessment_id=row["input_assessment_id"],
        proposed_title=row["proposed_title"],
        proposed_description=row["proposed_description"],
        rationale=row["rationale"],
        key_changes=key_changes,
        status=row["status"],
        created_at=row["created_at"],
    )


def _row_to_revision_response(
    row: sqlite3.Row,
    assessment: AssessmentResult | None = None,
) -> IdeaRevisionResponse:
    return IdeaRevisionResponse(
        id=row["id"],
        session_id=row["session_id"],
        proposal_id=row["proposal_id"],
        revision_number=row["revision_number"],
        title=row["title"],
        description=row["description"],
        assessment_id=row["assessment_id"],
        created_at=row["created_at"],
        assessment=assessment,
    )


def _compute_score_comparison(
    old_assessment: AssessmentResult,
    new_assessment: AssessmentResult,
) -> ScoreComparison:
    old_crit_map = {c.criterion: c.score for c in old_assessment.criteria}
    criteria_deltas: list[ScoreDelta] = []

    for new_crit in new_assessment.criteria:
        old_val = old_crit_map.get(new_crit.criterion, 0)
        criteria_deltas.append(
            ScoreDelta(
                criterion=new_crit.criterion,
                old_score=old_val,
                new_score=new_crit.score,
                delta=new_crit.score - old_val,
            )
        )

    final_delta = round(new_assessment.final_score - old_assessment.final_score, 2)

    return ScoreComparison(
        old_final_score=old_assessment.final_score,
        new_final_score=new_assessment.final_score,
        final_score_delta=final_delta,
        old_classification=old_assessment.classification,
        new_classification=new_assessment.classification,
        criteria_deltas=criteria_deltas,
    )


class ImprovementService:
    def __init__(self, gemini: GeminiService) -> None:
        self._gemini = gemini

    def start_session(
        self, idea_id: int, user_id: int
    ) -> ImprovementSessionResponse:
        _load_idea(idea_id, user_id)

        # 1. Check if there's already an active session
        existing_active = store.get_active_session_for_idea(idea_id, user_id)
        if existing_active is not None:
            return _row_to_session_response(existing_active)

        # 2. Get latest assessment for baseline
        from assessment_store import list_assessments
        assessments = list_assessments(idea_id, user_id)
        if not assessments:
            raise InvalidSessionStateError(
                "An idea must have at least one completed assessment before starting an improvement session."
            )

        latest_assessment_row = assessments[0]
        # Requirement 3: Verify the assessment belongs to the requested idea
        if latest_assessment_row["idea_id"] != idea_id:
            raise AssessmentMismatchError("Assessment does not belong to this idea.")

        # Create new session
        row = store.create_session(
            user_id=user_id,
            idea_id=idea_id,
            base_assessment_id=latest_assessment_row["id"],
        )
        return _row_to_session_response(row)

    def get_active_session_detail(
        self, idea_id: int, user_id: int
    ) -> ImprovementSessionDetailResponse | None:
        _load_idea(idea_id, user_id)
        session_row = store.get_active_session_for_idea(idea_id, user_id)
        if session_row is None:
            return None

        return self.get_session_detail(session_row["id"], user_id)

    def get_session_detail(
        self, session_id: int, user_id: int
    ) -> ImprovementSessionDetailResponse:
        session_row = store.get_session(session_id, user_id)
        if session_row is None:
            raise SessionNotFoundError("Improvement session not found.")

        # Determine current text and current assessment
        current_rev_id = session_row["current_revision_id"]
        if current_rev_id is not None:
            rev_row = store.get_revision(current_rev_id, user_id)
            if rev_row is None:
                raise InvalidSessionStateError("Current revision missing from database.")
            current_text = {
                "title": rev_row["title"],
                "description": rev_row["description"],
            }
            ass_row = store.get_assessment_by_id(rev_row["assessment_id"], user_id)
        else:
            idea = _load_idea(session_row["idea_id"], user_id)
            current_text = {
                "title": idea.title,
                "description": idea.description,
            }
            ass_row = store.get_assessment_by_id(
                session_row["base_assessment_id"], user_id
            )

        if ass_row is None:
            raise InvalidSessionStateError("Session assessment missing from database.")

        current_assessment = _row_to_result(ass_row)

        # Revisions
        revisions_rows = store.list_revisions(session_id, user_id)
        revisions = []
        for r in revisions_rows:
            r_ass = store.get_assessment_by_id(r["assessment_id"], user_id)
            revisions.append(
                _row_to_revision_response(
                    r, _row_to_result(r_ass) if r_ass else None
                )
            )

        # Pending proposal
        pending_row = store.get_pending_proposal(session_id, user_id)
        pending_proposal = _row_to_proposal_response(pending_row) if pending_row else None

        # Proposal history
        all_proposals = [
            _row_to_proposal_response(p)
            for p in store.list_proposals(session_id, user_id)
        ]

        return ImprovementSessionDetailResponse(
            session=_row_to_session_response(session_row),
            current_text=current_text,
            current_assessment=current_assessment,
            revisions=revisions,
            pending_proposal=pending_proposal,
            proposal_history=all_proposals,
        )

    def propose(
        self, idea_id: int, session_id: int, user_id: int
    ) -> ImprovementProposalResponse:
        session_row = store.get_session(session_id, user_id)
        if session_row is None:
            raise SessionNotFoundError("Session not found.")
        if session_row["idea_id"] != idea_id:
            raise SessionNotFoundError("Session does not belong to this idea.")
        if session_row["status"] != "active":
            raise InvalidSessionStateError(
                f"Session is {session_row['status']}, cannot propose."
            )
        if session_row["accepted_revision_count"] >= 5:
            raise MaximumRevisionsReachedError("Maximum 5 accepted revisions reached.")

        # Determine input text and assessment
        current_rev_id = session_row["current_revision_id"]
        if current_rev_id is not None:
            rev_row = store.get_revision(current_rev_id, user_id)
            if not rev_row:
                raise InvalidSessionStateError("Active revision record not found.")
            input_title = rev_row["title"]
            input_description = rev_row["description"]
            input_assessment_id = rev_row["assessment_id"]
        else:
            idea = _load_idea(idea_id, user_id)
            input_title = idea.title
            input_description = idea.description
            input_assessment_id = session_row["base_assessment_id"]

        ass_row = store.get_assessment_by_id(input_assessment_id, user_id)
        if not ass_row:
            raise InvalidSessionStateError("Input assessment record not found.")

        ass_result = _row_to_result(ass_row)
        latest_assessment_dict = ass_result.model_dump()

        # Supersede any existing pending proposal
        store.supersede_pending_proposals(session_id, user_id)

        next_attempt = store.get_next_proposal_attempt(session_id, user_id)
        iteration_number = session_row["accepted_revision_count"] + 1

        # Call Gemini outside any DB transaction
        proposal_content = self._gemini.generate_improvement_proposal(
            current_title=input_title,
            current_description=input_description,
            latest_assessment=latest_assessment_dict,
            iteration_number=iteration_number,
        )

        row = store.insert_proposal(
            user_id=user_id,
            session_id=session_id,
            proposal_attempt=next_attempt,
            input_revision_id=current_rev_id,
            input_assessment_id=input_assessment_id,
            proposed_title=proposal_content.proposed_title,
            proposed_description=proposal_content.proposed_description,
            rationale=proposal_content.rationale,
            key_changes=proposal_content.key_changes,
        )

        return _row_to_proposal_response(row)

    def action_proposal(
        self,
        idea_id: int,
        session_id: int,
        proposal_id: int,
        action: str,
        user_id: int,
    ) -> ProposalActionResponse:
        session_row = store.get_session(session_id, user_id)
        if session_row is None or session_row["idea_id"] != idea_id:
            raise SessionNotFoundError("Session not found.")
        if session_row["status"] != "active":
            raise InvalidSessionStateError(f"Session is {session_row['status']}.")

        proposal_row = store.get_proposal(proposal_id, user_id)
        if proposal_row is None or proposal_row["session_id"] != session_id:
            raise ProposalNotFoundError("Proposal not found.")
        if proposal_row["status"] != "pending":
            raise InvalidProposalStateError(f"Proposal is already {proposal_row['status']}.")

        if action == "reject":
            store.update_proposal_status(proposal_id, user_id, "rejected")
            updated_session = store.get_session(session_id, user_id)
            updated_proposal = store.get_proposal(proposal_id, user_id)
            return ProposalActionResponse(
                action="reject",
                session=_row_to_session_response(updated_session),
                proposal=_row_to_proposal_response(updated_proposal),
            )

        elif action == "regenerate":
            # Mark current proposal as superseded
            store.update_proposal_status(proposal_id, user_id, "superseded")
            # Generate new proposal
            next_proposal = self.propose(idea_id, session_id, user_id)
            updated_session = store.get_session(session_id, user_id)
            updated_proposal = store.get_proposal(proposal_id, user_id)
            return ProposalActionResponse(
                action="regenerate",
                session=_row_to_session_response(updated_session),
                proposal=_row_to_proposal_response(updated_proposal),
                next_proposal=next_proposal,
            )

        elif action == "accept":
            if session_row["accepted_revision_count"] >= 5:
                raise MaximumRevisionsReachedError("Maximum 5 accepted revisions reached.")

            # Load the input assessment to score against and compare
            input_ass_row = store.get_assessment_by_id(
                proposal_row["input_assessment_id"], user_id
            )
            if input_ass_row is None:
                raise InvalidSessionStateError("Base assessment record missing.")
            old_assessment = _row_to_result(input_ass_row)

            # Pre-evaluate using Gemini OUTSIDE SQLite write transaction
            idea = _load_idea(idea_id, user_id)
            scoring_payload = self._gemini.score(
                idea=idea,
                analysis=old_assessment,
                confirmed_title=proposal_row["proposed_title"],
                confirmed_description=proposal_row["proposed_description"],
            )
            scoring_result = score_assessment(scoring_payload.criteria)

            analysis_dict = scoring_payload.narrative.model_dump()
            scoring_dict = {
                "criteria": [
                    {
                        "criterion": c.criterion,
                        "score": c.score,
                        "weight": c.weight,
                        "weighted_score": c.weighted_score,
                        "reasoning": c.reasoning,
                        "evidence": c.evidence,
                        "assumptions": c.assumptions,
                    }
                    for c in scoring_result.criteria
                ],
                "final_score": scoring_result.final_score,
                "classification": scoring_result.classification,
            }

            # Atomic short database transaction
            updated_session_row, updated_proposal_row, new_revision_row = store.atomic_accept_proposal(
                user_id=user_id,
                session_id=session_id,
                proposal_id=proposal_id,
                idea_id=idea_id,
                proposed_title=proposal_row["proposed_title"],
                proposed_description=proposal_row["proposed_description"],
                analysis_payload=analysis_dict,
                scoring_payload=scoring_dict,
                final_score=scoring_result.final_score,
                classification=scoring_result.classification,
            )

            # Build response
            new_ass_row = store.get_assessment_by_id(
                new_revision_row["assessment_id"], user_id
            )
            new_assessment = _row_to_result(new_ass_row)
            comparison = _compute_score_comparison(old_assessment, new_assessment)

            return ProposalActionResponse(
                action="accept",
                session=_row_to_session_response(updated_session_row),
                proposal=_row_to_proposal_response(updated_proposal_row),
                revision=_row_to_revision_response(new_revision_row, new_assessment),
                comparison=comparison,
            )

        else:
            raise ValueError(f"Unknown action: {action}")

    def stop_session(
        self, idea_id: int, session_id: int, user_id: int
    ) -> ImprovementSessionResponse:
        session_row = store.get_session(session_id, user_id)
        if session_row is None or session_row["idea_id"] != idea_id:
            raise SessionNotFoundError("Session not found.")
        if session_row["status"] != "active":
            raise InvalidSessionStateError(f"Session is already {session_row['status']}.")

        store.supersede_pending_proposals(session_id, user_id)
        store.update_session_status(session_id, user_id, "cancelled")

        updated = store.get_session(session_id, user_id)
        return _row_to_session_response(updated)
