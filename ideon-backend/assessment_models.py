"""Pydantic models for the assessment workflow and API responses."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


def _clean_text(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("must not be empty")

    return value


def _clean_optional_text(value: str) -> str:
    return value.strip()


def _clean_text_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]

    if any(not item for item in cleaned):
        raise ValueError("items must not be empty")

    return cleaned


class IdeaSnapshot(BaseModel):
    id: int
    title: str
    description: str


class AssessmentNarrative(BaseModel):
    """Analysis fields shared by preparation and final scoring."""

    summary: str
    key_strengths: list[str]
    key_weaknesses: list[str]
    missing_information: list[str]
    critical_assumptions: list[str]
    uncertainty_notes: list[str]

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator(
        "key_strengths",
        "key_weaknesses",
        "missing_information",
        "critical_assumptions",
        "uncertainty_notes",
    )
    @classmethod
    def list_items_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class AssessmentAnalysis(AssessmentNarrative):
    """Preparation output. It intentionally contains no scores."""

    clarifying_questions: list[str] = []
    proposed_refined_title: str
    proposed_refined_description: str

    @field_validator("clarifying_questions")
    @classmethod
    def at_most_two_questions(cls, value: list[str]) -> list[str]:
        cleaned = _clean_text_list(value)

        if len(cleaned) > 2:
            raise ValueError("must contain at most two questions")

        return cleaned

    @field_validator("proposed_refined_title", "proposed_refined_description")
    @classmethod
    def proposed_text_must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)


class PrepareResponse(BaseModel):
    idea: IdeaSnapshot
    analysis: AssessmentAnalysis


class ClarificationAnswer(BaseModel):
    question: str
    answer: str = ""

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("answer")
    @classmethod
    def clean_answer(cls, value: str) -> str:
        return _clean_optional_text(value)


class RefineRequest(BaseModel):
    analysis: AssessmentAnalysis
    answers: list[ClarificationAnswer] = []


class RefinedIdea(BaseModel):
    title: str
    description: str

    @field_validator("title", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)


class ScoreRequest(BaseModel):
    confirmed: bool = False
    analysis: AssessmentNarrative
    confirmed_title: str
    confirmed_description: str

    @field_validator("confirmed_title", "confirmed_description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return _clean_text(value)


class CriterionResult(BaseModel):
    criterion: str
    score: int
    weight: float
    weighted_score: float
    reasoning: str
    evidence: str
    assumptions: str


class AssessmentResult(AssessmentNarrative):
    id: int
    idea_id: int
    evaluated_title: str
    evaluated_description: str
    criteria: list[CriterionResult]
    final_score: float
    classification: str
    created_at: str
