"""Orchestration for the prepare -> refine -> confirm -> score workflow."""

from __future__ import annotations

import json
from contextlib import closing

from assessment_models import (
    AssessmentResult,
    CriterionResult,
    IdeaSnapshot,
    PrepareResponse,
    RefineRequest,
    RefinedIdea,
    ScoreRequest,
)
from assessment_store import insert_assessment, list_assessments
from database import get_connection
from gemini_service import GeminiService
from scoring import score_assessment


class IdeaNotFoundError(LookupError):
    """The requested idea does not exist."""


class ConfirmationRequiredError(ValueError):
    """The user has not explicitly approved the refined idea."""


def _load_idea(idea_id: int, user_id: int) -> IdeaSnapshot:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, title, description
            FROM ideas
            WHERE id = ? AND user_id = ?
            """,
            (idea_id, user_id),
        ).fetchone()

    if row is None:
        raise IdeaNotFoundError("Idea not found.")

    return IdeaSnapshot(**dict(row))


def _row_to_result(row) -> AssessmentResult:
    analysis = json.loads(row["analysis_json"])
    scoring = json.loads(row["scoring_json"])

    return AssessmentResult(
        id=row["id"],
        idea_id=row["idea_id"],
        evaluated_title=row["idea_title"],
        evaluated_description=row["idea_description"],
        summary=analysis["summary"],
        key_strengths=analysis["key_strengths"],
        key_weaknesses=analysis["key_weaknesses"],
        missing_information=analysis["missing_information"],
        critical_assumptions=analysis["critical_assumptions"],
        uncertainty_notes=analysis["uncertainty_notes"],
        criteria=[CriterionResult(**criterion) for criterion in scoring["criteria"]],
        final_score=row["final_score"],
        classification=row["classification"],
        created_at=row["created_at"],
    )


class AssessmentService:
    def __init__(self, gemini: GeminiService) -> None:
        self._gemini = gemini

    def prepare(self, idea_id: int, user_id: int) -> PrepareResponse:
        idea = _load_idea(idea_id, user_id)
        analysis = self._gemini.prepare(idea)

        return PrepareResponse(idea=idea, analysis=analysis)

    def refine(
        self, idea_id: int, request: RefineRequest, user_id: int
    ) -> RefinedIdea:
        idea = _load_idea(idea_id, user_id)
        answers = [
            {"question": answer.question, "answer": answer.answer}
            for answer in request.answers
            if answer.answer.strip()
        ]

        return self._gemini.refine(idea, request.analysis, answers)

    def score(
        self, idea_id: int, request: ScoreRequest, user_id: int
    ) -> AssessmentResult:
        if request.confirmed is not True:
            raise ConfirmationRequiredError(
                "The refined idea must be explicitly approved before scoring."
            )

        idea = _load_idea(idea_id, user_id)
        payload = self._gemini.score(
            idea,
            request.analysis,
            request.confirmed_title,
            request.confirmed_description,
        )
        result = score_assessment(payload.criteria)

        analysis = payload.narrative.model_dump()
        scoring = {
            "criteria": [
                {
                    "criterion": criterion.criterion,
                    "score": criterion.score,
                    "weight": criterion.weight,
                    "weighted_score": criterion.weighted_score,
                    "reasoning": criterion.reasoning,
                    "evidence": criterion.evidence,
                    "assumptions": criterion.assumptions,
                }
                for criterion in result.criteria
            ],
            "final_score": result.final_score,
            "classification": result.classification,
        }

        row = insert_assessment(
            user_id=user_id,
            idea_id=idea_id,
            idea_title=request.confirmed_title,
            idea_description=request.confirmed_description,
            analysis=analysis,
            scoring=scoring,
            final_score=result.final_score,
            classification=result.classification,
        )

        return _row_to_result(row)

    def history(self, idea_id: int, user_id: int) -> list[AssessmentResult]:
        _load_idea(idea_id, user_id)

        return [
            _row_to_result(row) for row in list_assessments(idea_id, user_id)
        ]
