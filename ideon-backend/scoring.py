"""Deterministic assessment scoring.

This module is the single authoritative source for the rubric names, weights,
score calculation, and classification. It does not import or call Gemini.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class ScoringError(ValueError):
    """Raised when an assessment payload cannot be scored."""


@dataclass(frozen=True)
class RubricCriterion:
    name: str
    weight: float


# The order is also the order used in prompts and responses.
RUBRIC: tuple[RubricCriterion, ...] = (
    RubricCriterion(name="Impact", weight=0.30),
    RubricCriterion(name="Feasibility", weight=0.25),
    RubricCriterion(name="Efficiency & Cost", weight=0.15),
    RubricCriterion(name="Risk Control", weight=0.15),
    RubricCriterion(name="Goal Alignment", weight=0.15),
)

RUBRIC_BY_NAME: dict[str, RubricCriterion] = {
    criterion.name: criterion for criterion in RUBRIC
}


@dataclass(frozen=True)
class CriterionScore:
    criterion: str
    score: int
    weight: float
    weighted_score: float
    reasoning: str
    evidence: str
    assumptions: str


@dataclass(frozen=True)
class ScoringResult:
    criteria: tuple[CriterionScore, ...]
    final_score: float
    classification: str


def classify(final_score: float) -> str:
    """Return the classification for an already-calculated final score."""
    if final_score >= 80:
        return "Strong"
    if final_score >= 65:
        return "Promising"
    if final_score >= 50:
        return "Needs Improvement"
    return "Weak"


def _require_text(item: Mapping[str, Any], field: str, position: int) -> str:
    value = item.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ScoringError(
            f"Assessment criterion {position + 1} is missing a valid "
            f"'{field}' value."
        )

    return value.strip()


def _validate_score(value: Any, name: str) -> int:
    # bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoringError(f"Score for '{name}' must be an integer from 0 to 100.")

    if value < 0 or value > 100:
        raise ScoringError(f"Score for '{name}' must be between 0 and 100.")

    return value


def score_assessment(criteria: Sequence[Mapping[str, Any]]) -> ScoringResult:
    """Validate AI criterion scores and calculate the weighted final score.

    Every rubric criterion must be present exactly once. The final score and
    classification are always computed here, never supplied by the AI.
    """
    if not isinstance(criteria, list) or len(criteria) != len(RUBRIC):
        raise ScoringError(
            f"Assessment must contain exactly {len(RUBRIC)} criteria."
        )

    validated: list[CriterionScore] = []
    seen: set[str] = set()

    for index, item in enumerate(criteria):
        if not isinstance(item, Mapping):
            raise ScoringError(
                f"Assessment criterion {index + 1} must be an object."
            )

        name = _require_text(item, "criterion", index)

        if name not in RUBRIC_BY_NAME:
            raise ScoringError(f"Unknown assessment criterion: '{name}'.")

        if name in seen:
            raise ScoringError(f"Assessment criterion '{name}' appears more than once.")

        seen.add(name)

        raw_score = _validate_score(item.get("score"), name)
        reasoning = _require_text(item, "reasoning", index)
        evidence = _require_text(item, "evidence", index)
        assumptions = _require_text(item, "assumptions", index)

        rubric = RUBRIC_BY_NAME[name]
        weighted_score = round(raw_score * rubric.weight, 4)

        validated.append(
            CriterionScore(
                criterion=name,
                score=raw_score,
                weight=rubric.weight,
                weighted_score=weighted_score,
                reasoning=reasoning,
                evidence=evidence,
                assumptions=assumptions,
            )
        )

    missing = {criterion.name for criterion in RUBRIC} - seen

    if missing:
        raise ScoringError(
            "Assessment is missing criteria: " + ", ".join(sorted(missing)) + "."
        )

    # Preserve the authoritative rubric order in the result.
    ordered = sorted(
        validated,
        key=lambda criterion: [item.name for item in RUBRIC].index(
            criterion.criterion
        ),
    )

    final_score = round(sum(item.weighted_score for item in ordered), 2)

    return ScoringResult(
        criteria=tuple(ordered),
        final_score=final_score,
        classification=classify(final_score),
    )
