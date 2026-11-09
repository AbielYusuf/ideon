"""Pydantic models for the Phase 5 Manual Improvement Loop."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, field_validator

from assessment_models import AssessmentResult, _clean_text, _clean_text_list


class ImprovementSessionResponse(BaseModel):
    id: int
    idea_id: int
    base_assessment_id: int
    current_revision_id: int | None
    status: Literal["active", "completed", "cancelled"]
    accepted_revision_count: int
    created_at: str
    updated_at: str


class ImprovementProposalResponse(BaseModel):
    id: int
    session_id: int
    proposal_attempt: int
    input_revision_id: int | None
    input_assessment_id: int
    proposed_title: str
    proposed_description: str
    rationale: str
    key_changes: list[str]
    status: Literal["pending", "accepted", "rejected", "superseded"]
    created_at: str


class IdeaRevisionResponse(BaseModel):
    id: int
    session_id: int
    proposal_id: int
    revision_number: int
    title: str
    description: str
    assessment_id: int
    created_at: str
    assessment: AssessmentResult | None = None


class ProposalActionRequest(BaseModel):
    action: Literal["accept", "reject", "regenerate"]


class ScoreDelta(BaseModel):
    criterion: str
    old_score: int
    new_score: int
    delta: int


class ScoreComparison(BaseModel):
    old_final_score: float
    new_final_score: float
    final_score_delta: float
    old_classification: str
    new_classification: str
    criteria_deltas: list[ScoreDelta]


class ProposalActionResponse(BaseModel):
    action: str
    session: ImprovementSessionResponse
    proposal: ImprovementProposalResponse
    revision: IdeaRevisionResponse | None = None
    comparison: ScoreComparison | None = None
    next_proposal: ImprovementProposalResponse | None = None


class ImprovementSessionDetailResponse(BaseModel):
    session: ImprovementSessionResponse
    current_text: dict[str, str]  # title, description
    current_assessment: AssessmentResult
    revisions: list[IdeaRevisionResponse]
    pending_proposal: ImprovementProposalResponse | None = None
    proposal_history: list[ImprovementProposalResponse] = []


class GeneratedProposalContent(BaseModel):
    proposed_title: str
    proposed_description: str
    rationale: str
    key_changes: list[str]

    @field_validator("proposed_title", "proposed_description", "rationale")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("key_changes")
    @classmethod
    def key_changes_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)
